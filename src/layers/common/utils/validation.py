"""
Input validation utilities for AnyCompany Hotel platform.

Provides helpers for parsing request bodies, validating required fields,
UUID formats, date formats, date ranges, and pagination parameters.
"""

import json
import uuid as uuid_module
from datetime import date, datetime

from utils.response import bad_request


def parse_body(event: dict) -> dict | None:
    """
    Parse the JSON body from an API Gateway Lambda proxy event.

    Handles both raw dict bodies (from test events) and JSON-encoded
    string bodies. Returns None if the body is missing or invalid JSON.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Parsed dict or None if body is missing/invalid.
    """
    body = event.get("body")
    if body is None:
        return None
    if isinstance(body, dict):
        return body
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None


def require_fields(data: dict | None, fields: list[str]) -> dict | None:
    """
    Validate that all required fields are present and non-None in the data.

    Args:
        data: The parsed request body dict.
        fields: List of required field names.

    Returns:
        None if all fields are present, or a 400 error response dict
        listing the missing fields.
    """
    if data is None:
        return bad_request("Request body is required.")

    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        return bad_request(f"Missing required fields: {', '.join(missing)}")

    return None


def validate_uuid(value: str, field_name: str | None = None):
    """
    Validate that a string is a properly formatted UUID (v4).

    Two calling styles are supported:
    1. Bool style: ``validate_uuid(value)`` → returns True/False.
    2. Raising style: ``validate_uuid(value, field_name)`` → returns the
       normalised string value on success, raises ValueError on failure.

    Args:
        value: String to validate.
        field_name: Optional name for error messages. When provided, the
            function returns the string value on success and raises
            ValueError on failure. When omitted, returns a bool.

    Returns:
        - If ``field_name`` is None: True/False.
        - If ``field_name`` is provided: the string value.
    """
    try:
        uuid_module.UUID(str(value), version=4)
        valid = True
    except (ValueError, AttributeError, TypeError):
        valid = False

    if field_name is not None:
        if not valid:
            raise ValueError(f"{field_name} must be a valid UUID")
        return str(value)

    return valid


def validate_date(value: str) -> date | None:
    """
    Validate and parse a YYYY-MM-DD date string.

    Args:
        value: Date string in YYYY-MM-DD format.

    Returns:
        A date object if valid, or None if the format is invalid.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def validate_date_range(check_in: str, check_out: str) -> dict | None:
    """
    Validate a check-in / check-out date range.

    Ensures both dates are valid YYYY-MM-DD format, that check_in is
    strictly before check_out, and that both dates are in the future
    (today or later for check_in).

    Args:
        check_in: Check-in date string (YYYY-MM-DD).
        check_out: Check-out date string (YYYY-MM-DD).

    Returns:
        None if the range is valid, or a 400 error response dict
        describing the validation failure.
    """
    ci = validate_date(check_in)
    if ci is None:
        return bad_request("Invalid check_in date format. Expected YYYY-MM-DD.")

    co = validate_date(check_out)
    if co is None:
        return bad_request("Invalid check_out date format. Expected YYYY-MM-DD.")

    today = date.today()

    if ci < today:
        return bad_request("check_in date must be today or in the future.")

    if co <= ci:
        return bad_request("check_out date must be after check_in date.")

    return None


def validate_pagination(event: dict) -> dict:
    """
    Extract and validate pagination parameters from query string.

    Reads 'page' and 'limit' from queryStringParameters with defaults
    of page=1 and limit=20. Enforces a maximum limit of 100.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Dict with 'page', 'limit', and 'offset' keys.
    """
    params = event.get("queryStringParameters") or {}

    try:
        page = int(params.get("page", 1))
    except (ValueError, TypeError):
        page = 1

    try:
        limit = int(params.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20

    if page < 1:
        page = 1
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    offset = (page - 1) * limit

    return {
        "page": page,
        "limit": limit,
        "offset": offset,
    }

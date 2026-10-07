"""
Lambda handler for GET /properties/{propertyId}/room-types/{roomTypeId}.

Retrieves a single room type by ID for a given property.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, not_found, ok, server_error
from utils.validation import validate_uuid

logger = get_logger("property")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, (UUID,)):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def handler(event, context):
    """Get a single room type by ID."""
    try:
        property_id = event.get("pathParameters", {}).get("propertyId")
        room_type_id = event.get("pathParameters", {}).get("roomTypeId")

        if not property_id or not validate_uuid(property_id):
            return bad_request("A valid propertyId is required.")

        if not room_type_id or not validate_uuid(room_type_id):
            return bad_request("A valid roomTypeId is required.")

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM room_types
                    WHERE room_type_id = %s AND property_id = %s
                    """,
                    (room_type_id, property_id),
                )
                room_type = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not room_type:
            return not_found(f"Room type {room_type_id} not found for property {property_id}.")

        return ok(_serialize_row(room_type))

    except Exception:
        logger.exception("Error getting room type")
        return server_error("Failed to get room type.")

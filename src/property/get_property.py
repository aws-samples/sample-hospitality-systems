"""
Lambda handler for GET /properties/{propertyId}.

Retrieves a single property by ID with its associated room types
as a nested array.
"""

from utils.logger import get_logger
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.response import ok, not_found, bad_request, server_error, transform_keys
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
    """Get a single property with its room types."""
    try:
        property_id = event.get("pathParameters", {}).get("propertyId")

        if not property_id or not validate_uuid(property_id):
            return bad_request("A valid propertyId is required.")

        conn = get_conn()
        try:
            # Fetch property
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM properties WHERE property_id = %s",
                    (property_id,),
                )
                property_row = cur.fetchone()

            if not property_row:
                return not_found(f"Property {property_id} not found.")

            # Fetch room types for this property
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM room_types
                    WHERE property_id = %s AND is_active = TRUE
                    ORDER BY sort_order ASC, name ASC
                    """,
                    (property_id,),
                )
                room_type_rows = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        property_data = _serialize_row(property_row)
        property_data["room_types"] = [_serialize_row(rt) for rt in room_type_rows]

        return ok(property_data)

    except Exception as e:
        logger.exception("Error getting property")
        return server_error("Failed to get property.")

"""
Lambda handler for GET /properties/{propertyId}/room-types.

Lists all active room types for a property, including base rates
and the Best Available Rate (BAR) from active PUBLIC rate plans.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, ok, server_error
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
    """List all active room types for a property with BAR rates."""
    try:
        property_id = event.get("pathParameters", {}).get("propertyId")

        if not property_id or not validate_uuid(property_id):
            return bad_request("A valid propertyId is required.")

        conn = get_conn()
        try:
            # Fetch active room types for the property
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
                room_types = cur.fetchall()

            # Fetch BAR (Best Available Rate) from active PUBLIC rate plans
            room_type_ids = [rt["room_type_id"] for rt in room_types]

            bar_rates = {}
            if room_type_ids:
                # Static query; the id list is bound as a single array parameter
                # via = ANY(%s) (no dynamic placeholder assembly).
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT rp_prices.room_type_id,
                               rp_prices.rate_plan_id,
                               rp.name AS rate_plan_name,
                               rp_prices.price_per_night AS base_price
                        FROM rate_plan_room_prices rp_prices
                        JOIN rate_plans rp ON rp.rate_plan_id = rp_prices.rate_plan_id
                        WHERE rp_prices.room_type_id = ANY(%s)
                          AND rp.is_active = TRUE
                          AND rp.type = 'PUBLIC'
                        ORDER BY rp_prices.price_per_night ASC
                        """,
                        (room_type_ids,),
                    )
                    bar_rows = cur.fetchall()

                # Keep the lowest price per room type (BAR)
                for row in bar_rows:
                    rt_id = str(row["room_type_id"])
                    if rt_id not in bar_rates:
                        bar_rates[rt_id] = _serialize_row(row)

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Combine room types with BAR rates
        result = []
        for rt in room_types:
            serialized = _serialize_row(rt)
            rt_id = str(rt["room_type_id"])
            serialized["best_available_rate"] = bar_rates.get(rt_id)
            result.append(serialized)

        return ok(result)

    except Exception:
        logger.exception("Error listing room types")
        return server_error("Failed to list room types.")

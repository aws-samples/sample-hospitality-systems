"""
Lambda handler for GET /availability.

Checks room availability for a property across a date range. For each room
type, finds the minimum available inventory across all dates in the range,
then filters by occupancy requirements. Joins with active PUBLIC rate plans
to return nightly rates.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, ok, server_error
from utils.validation import validate_date, validate_date_range, validate_uuid

logger = get_logger("crs")


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
    """Check room availability for a property and date range."""
    try:
        params = event.get("queryStringParameters") or {}

        property_id = params.get("propertyId")
        check_in = params.get("checkIn")
        check_out = params.get("checkOut")
        adults = params.get("adults", "1")

        # Validate required params
        if not property_id:
            return bad_request("propertyId is required.")
        if not validate_uuid(property_id):
            return bad_request("propertyId must be a valid UUID.")
        if not check_in:
            return bad_request("checkIn date is required.")
        if not check_out:
            return bad_request("checkOut date is required.")

        # Validate dates
        date_error = validate_date_range(check_in, check_out)
        if date_error:
            return date_error

        try:
            adults = int(adults)
            if adults < 1:
                return bad_request("adults must be at least 1.")
        except (ValueError, TypeError):
            return bad_request("adults must be a valid integer.")

        ci_date = validate_date(check_in)
        co_date = validate_date(check_out)

        conn = get_conn()
        try:
            # Find room types with minimum availability across all dates in range
            # and filter by max_occupancy
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        rt.room_type_id,
                        rt.name AS room_type_name,
                        rt.description,
                        rt.max_occupancy,
                        rt.base_rate,
                        rt.bed_configuration,
                        rt.square_feet,
                        rt.amenities,
                        MIN(a.total_inventory - a.sold) AS min_available
                    FROM room_types rt
                    JOIN availability a ON a.room_type_id = rt.room_type_id
                    WHERE rt.property_id = %s
                      AND rt.is_active = TRUE
                      AND a.date >= %s
                      AND a.date < %s
                      AND rt.max_occupancy >= %s
                    GROUP BY rt.room_type_id, rt.name, rt.description,
                             rt.max_occupancy, rt.base_rate, rt.bed_configuration,
                             rt.square_feet, rt.amenities
                    HAVING MIN(a.total_inventory - a.sold) > 0
                    ORDER BY rt.base_rate ASC
                    """,
                    (property_id, ci_date, co_date, adults),
                )
                available_rooms = cur.fetchall()

            # Get the room type IDs that are available
            room_type_ids = [row["room_type_id"] for row in available_rooms]

            # Fetch rate plan prices for available room types
            rates_by_room = {}
            if room_type_ids:
                # Static query; the id list is bound as a single array parameter
                # via = ANY(%s) (no dynamic placeholder assembly).
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            rp_prices.room_type_id,
                            rp_prices.rate_plan_id,
                            rp.name AS rate_plan_name,
                            rp_prices.price_per_night AS nightly_rate,
                            rp.cancellation_policy
                        FROM rate_plan_room_prices rp_prices
                        JOIN rate_plans rp ON rp.rate_plan_id = rp_prices.rate_plan_id
                        WHERE rp_prices.room_type_id = ANY(%s)
                          AND rp.is_active = TRUE
                          AND rp.type = 'PUBLIC'
                        ORDER BY rp_prices.price_per_night ASC
                        """,
                        (room_type_ids,),
                    )
                    rate_rows = cur.fetchall()

                for rate_row in rate_rows:
                    rt_id = str(rate_row["room_type_id"])
                    if rt_id not in rates_by_room:
                        rates_by_room[rt_id] = []
                    rates_by_room[rt_id].append(_serialize_row(rate_row))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Calculate number of nights
        num_nights = (co_date - ci_date).days

        # Build response
        results = []
        for room in available_rooms:
            rt_id = str(room["room_type_id"])
            room_data = _serialize_row(room)
            room_data["available_rooms"] = room_data.pop("min_available")
            room_data["num_nights"] = num_nights

            # Attach rate plans
            rate_plans = rates_by_room.get(rt_id, [])
            for rp in rate_plans:
                nightly = Decimal(str(rp["nightly_rate"]))
                rp["total_before_tax"] = str(nightly * num_nights)
                rp["tax_amount"] = str(round(nightly * num_nights * Decimal("0.12"), 2))
                rp["total_with_tax"] = str(
                    round(nightly * num_nights * Decimal("1.12"), 2)
                )
            room_data["rate_plans"] = rate_plans
            results.append(room_data)

        return ok({
            "property_id": property_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "num_nights": num_nights,
            "available_room_types": results,
        })

    except Exception:
        logger.exception("Error checking availability")
        return server_error("Failed to check availability.")

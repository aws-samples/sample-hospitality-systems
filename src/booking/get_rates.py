"""
Lambda handler for GET /booking/rates.

Returns all available rate plans for a given property, room type, and date range.
Each rate plan includes a full pricing breakdown with nightly rates, date-specific
overrides, discounts, taxes, and cancellation policy.

Public endpoint — no authentication required.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, not_found, ok, server_error
from utils.validation import validate_date, validate_date_range, validate_uuid

logger = get_logger("booking")

TAX_RATE = Decimal("0.12")


def handler(event, context):
    """Get rate plans and pricing for a property/room type and date range."""
    try:
        params = event.get("queryStringParameters") or {}

        property_id = params.get("propertyId")
        room_type_id = params.get("roomTypeId")
        check_in = params.get("checkIn")
        check_out = params.get("checkOut")

        # Validate required params
        if not property_id:
            return bad_request("Missing required parameter: propertyId")
        if not room_type_id:
            return bad_request("Missing required parameter: roomTypeId")
        if not check_in:
            return bad_request("Missing required parameter: checkIn")
        if not check_out:
            return bad_request("Missing required parameter: checkOut")

        if not validate_uuid(property_id):
            return bad_request("Invalid propertyId format. Expected UUID.")
        if not validate_uuid(room_type_id):
            return bad_request("Invalid roomTypeId format. Expected UUID.")

        date_error = validate_date_range(check_in, check_out)
        if date_error:
            return date_error

        ci = validate_date(check_in)
        co = validate_date(check_out)
        num_nights = (co - ci).days

        conn = get_conn()
        try:
            # Verify property and room type exist and are active
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rt.room_type_id, rt.name AS room_type_name, rt.code AS room_type_code,
                           rt.max_occupancy, rt.base_rate, rt.bed_configuration,
                           p.name AS property_name, p.code AS property_code
                    FROM room_types rt
                    JOIN properties p ON p.property_id = rt.property_id
                    WHERE rt.room_type_id = %s
                      AND rt.property_id = %s
                      AND rt.is_active = TRUE
                      AND p.is_active = TRUE
                    """,
                    (room_type_id, property_id),
                )
                room_type = cur.fetchone()

            if not room_type:
                conn.commit()
                return not_found("Room type not found or not available at this property.")

            # Check availability across all dates in range
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS available_nights
                    FROM generate_series(%s::date, %s::date - INTERVAL '1 day', '1 day') AS d(dt)
                    LEFT JOIN availability a
                        ON a.room_type_id = %s AND a.date = d.dt::date
                    WHERE COALESCE(a.available, 0) + COALESCE(a.overbooking_allowance, 0) > 0
                    """,
                    (check_in, check_out, room_type_id),
                )
                avail_result = cur.fetchone()

            if avail_result["available_nights"] < num_nights:
                conn.commit()
                return ok({
                    "available": False,
                    "message": "Room type is not available for the full date range.",
                    "rate_options": [],
                })

            # Get all active rate plans for this property and room type
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        rp.rate_plan_id,
                        rp.code AS rate_plan_code,
                        rp.name AS rate_plan_name,
                        rp.description AS rate_plan_description,
                        rp.type AS rate_plan_type,
                        rp.discount_type,
                        rp.discount_value,
                        rp.cancellation_policy,
                        rp.restrictions,
                        rprp.price_per_night
                    FROM rate_plans rp
                    JOIN rate_plan_room_prices rprp
                        ON rprp.rate_plan_id = rp.rate_plan_id
                       AND rprp.room_type_id = %s
                    WHERE rp.property_id = %s
                      AND rp.is_active = TRUE
                      AND (rp.valid_from IS NULL OR rp.valid_from <= %s)
                      AND (rp.valid_to IS NULL OR rp.valid_to >= %s)
                    ORDER BY rprp.price_per_night ASC
                    """,
                    (room_type_id, property_id, check_in, check_out),
                )
                rate_plans = cur.fetchall()

            if not rate_plans:
                conn.commit()
                return ok({
                    "available": True,
                    "message": "No rate plans available for this room type and date range.",
                    "rate_options": [],
                })

            # Get all rate overrides for these rate plans in the date range
            rate_plan_ids = [rp["rate_plan_id"] for rp in rate_plans]
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rate_plan_id, override_date, override_amount, reason
                    FROM rate_overrides
                    WHERE rate_plan_id = ANY(%s)
                      AND room_type_id = %s
                      AND override_date >= %s
                      AND override_date < %s
                    """,
                    (rate_plan_ids, room_type_id, check_in, check_out),
                )
                overrides = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Index overrides by (rate_plan_id, date)
        override_map = {}
        for ov in overrides:
            key = (str(ov["rate_plan_id"]), ov["override_date"].isoformat())
            override_map[key] = ov["override_amount"]

        # Build rate options for each rate plan
        rate_options = []
        for rp in rate_plans:
            rp_id = str(rp["rate_plan_id"])
            base_price = Decimal(str(rp["price_per_night"]))
            discount_type = rp["discount_type"]
            discount_value = Decimal(str(rp["discount_value"])) if rp["discount_value"] else Decimal("0")

            nightly_rates = []
            total_before_tax = Decimal("0")

            current_date = ci
            while current_date < co:
                date_str = current_date.isoformat()
                override_key = (rp_id, date_str)

                # Check for date-specific override
                if override_key in override_map:
                    night_price = Decimal(str(override_map[override_key]))
                else:
                    night_price = base_price

                # Apply rate plan discount
                if discount_type == "PERCENTAGE" and discount_value > 0:
                    discount_amount = (night_price * discount_value / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    night_price = night_price - discount_amount
                elif discount_type == "FIXED_AMOUNT" and discount_value > 0:
                    night_price = night_price - discount_value
                    if night_price < 0:
                        night_price = Decimal("0")

                night_price = night_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_before_tax += night_price

                nightly_rates.append({
                    "date": date_str,
                    "price": str(night_price),
                    "is_override": override_key in override_map,
                })

                current_date += timedelta(days=1)

            tax_amount = (total_before_tax * TAX_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_after_tax = total_before_tax + tax_amount

            avg_nightly = (total_before_tax / num_nights).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ) if num_nights > 0 else Decimal("0")

            rate_options.append({
                "rate_plan_id": rp_id,
                "rate_plan_code": rp["rate_plan_code"],
                "rate_plan_name": rp["rate_plan_name"],
                "rate_plan_description": rp["rate_plan_description"],
                "rate_plan_type": rp["rate_plan_type"],
                "cancellation_policy": rp["cancellation_policy"],
                "discount_type": discount_type,
                "discount_value": str(discount_value),
                "nightly_rates": nightly_rates,
                "num_nights": num_nights,
                "average_nightly_rate": str(avg_nightly),
                "total_before_tax": str(total_before_tax),
                "tax_rate": str(TAX_RATE),
                "tax_amount": str(tax_amount),
                "total_after_tax": str(total_after_tax),
                "currency": "USD",
            })

        # Sort by total price ascending
        rate_options.sort(key=lambda r: Decimal(r["total_after_tax"]))

        return ok({
            "available": True,
            "property_id": property_id,
            "property_name": room_type["property_name"],
            "room_type_id": room_type_id,
            "room_type_name": room_type["room_type_name"],
            "room_type_code": room_type["room_type_code"],
            "max_occupancy": room_type["max_occupancy"],
            "bed_configuration": room_type["bed_configuration"],
            "check_in": check_in,
            "check_out": check_out,
            "num_nights": num_nights,
            "rate_options": rate_options,
        })

    except Exception:
        logger.exception("Error fetching rates")
        return server_error("Failed to fetch rates.")

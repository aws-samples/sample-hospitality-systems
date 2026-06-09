"""
Lambda handler for POST /booking/cart.

Creates a new booking cart with pricing calculated from the selected
rate plan. The cart expires after 30 minutes. Supports both authenticated
and unauthenticated (guest) users via optional JWT.

Public endpoint — authentication is optional.
"""

import json
from utils.logger import get_logger
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from utils.database import get_conn
from utils.response import ok, created, bad_request, not_found, server_error, transform_keys
from utils.auth import get_claims
from utils.validation import parse_body, require_fields, validate_uuid, validate_date, validate_date_range

logger = get_logger("booking")

TAX_RATE = Decimal("0.12")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def _calculate_pricing(conn, rate_plan_id, room_type_id, check_in_date, check_out_date):
    """
    Calculate pricing for a stay using rate_plan_room_prices and rate_overrides.

    Returns a dict with amount_per_night, total_before_tax, tax_amount,
    total_after_tax, nightly_rates, and num_nights.
    Returns None if the rate plan or pricing is not found.
    """
    ci = validate_date(check_in_date) if isinstance(check_in_date, str) else check_in_date
    co = validate_date(check_out_date) if isinstance(check_out_date, str) else check_out_date
    num_nights = (co - ci).days

    # Get rate plan details and base price
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rp.rate_plan_id, rp.discount_type, rp.discount_value,
                   rprp.price_per_night
            FROM rate_plans rp
            JOIN rate_plan_room_prices rprp
                ON rprp.rate_plan_id = rp.rate_plan_id
               AND rprp.room_type_id = %s
            WHERE rp.rate_plan_id = %s
              AND rp.is_active = TRUE
            """,
            (room_type_id, rate_plan_id),
        )
        rate_info = cur.fetchone()

    if not rate_info:
        return None

    base_price = Decimal(str(rate_info["price_per_night"]))
    discount_type = rate_info["discount_type"]
    discount_value = Decimal(str(rate_info["discount_value"])) if rate_info["discount_value"] else Decimal("0")

    # Get rate overrides for the date range
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT override_date, override_amount
            FROM rate_overrides
            WHERE rate_plan_id = %s
              AND room_type_id = %s
              AND override_date >= %s
              AND override_date < %s
            """,
            (rate_plan_id, room_type_id, check_in_date, check_out_date),
        )
        overrides = cur.fetchall()

    override_map = {}
    for ov in overrides:
        override_map[ov["override_date"].isoformat()] = ov["override_amount"]

    # Calculate nightly rates
    nightly_rates = []
    total_before_tax = Decimal("0")
    current_date = ci

    while current_date < co:
        date_str = current_date.isoformat()

        if date_str in override_map:
            night_price = Decimal(str(override_map[date_str]))
        else:
            night_price = base_price

        # Apply discount
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
        })

        current_date += timedelta(days=1)

    tax_amount = (total_before_tax * TAX_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_after_tax = total_before_tax + tax_amount

    avg_nightly = (total_before_tax / num_nights).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ) if num_nights > 0 else Decimal("0")

    return {
        "amount_per_night": avg_nightly,
        "total_before_tax": total_before_tax,
        "tax_amount": tax_amount,
        "total_after_tax": total_after_tax,
        "nightly_rates": nightly_rates,
        "num_nights": num_nights,
    }


def handler(event, context):
    """Create a new booking cart."""
    try:
        body = parse_body(event)
        field_error = require_fields(body, [
            "propertyId", "roomTypeId", "ratePlanId",
            "checkIn", "checkOut", "sessionId",
        ])
        if field_error:
            return field_error

        property_id = body["propertyId"]
        room_type_id = body["roomTypeId"]
        rate_plan_id = body["ratePlanId"]
        check_in = body["checkIn"]
        check_out = body["checkOut"]
        session_id = body["sessionId"]
        adults = body.get("adults", 1)
        children = body.get("children", 0)

        # Validate UUIDs
        for field_name, field_val in [("propertyId", property_id), ("roomTypeId", room_type_id), ("ratePlanId", rate_plan_id)]:
            if not validate_uuid(field_val):
                return bad_request(f"Invalid {field_name} format. Expected UUID.")

        # Validate dates
        date_error = validate_date_range(check_in, check_out)
        if date_error:
            return date_error

        ci = validate_date(check_in)
        co = validate_date(check_out)
        num_nights = (co - ci).days

        # Optional auth — extract guest_id if authenticated
        guest_id = None
        try:
            claims = get_claims(event)
            cognito_sub = claims["sub"]
        except (KeyError, TypeError):
            cognito_sub = None

        conn = get_conn()
        try:
            # If authenticated, look up guest_id
            if cognito_sub:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT guest_id FROM guests WHERE cognito_sub = %s",
                        (cognito_sub,),
                    )
                    guest_row = cur.fetchone()
                if guest_row:
                    guest_id = str(guest_row["guest_id"])

            # Verify property, room type, and rate plan exist
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rt.room_type_id
                    FROM room_types rt
                    JOIN properties p ON p.property_id = rt.property_id
                    WHERE rt.room_type_id = %s
                      AND rt.property_id = %s
                      AND rt.is_active = TRUE
                      AND p.is_active = TRUE
                    """,
                    (room_type_id, property_id),
                )
                if not cur.fetchone():
                    conn.commit()
                    return not_found("Room type not found or not available at this property.")

            # Verify rate plan exists for this property
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rate_plan_id FROM rate_plans
                    WHERE rate_plan_id = %s AND property_id = %s AND is_active = TRUE
                    """,
                    (rate_plan_id, property_id),
                )
                if not cur.fetchone():
                    conn.commit()
                    return not_found("Rate plan not found or not active for this property.")

            # Validate availability across all dates
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
                avail = cur.fetchone()

            if avail["available_nights"] < num_nights:
                conn.commit()
                return bad_request("Room type is not available for the full date range.")

            # Calculate pricing
            pricing = _calculate_pricing(conn, rate_plan_id, room_type_id, check_in, check_out)
            if pricing is None:
                conn.commit()
                return bad_request("Unable to calculate pricing for the selected rate plan and room type.")

            # Create the cart
            cart_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=30)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO booking_carts (
                        cart_id, guest_id, session_id, property_id, room_type_id,
                        rate_plan_id, check_in_date, check_out_date, adults, children,
                        amount_per_night, total_before_tax, total_after_tax,
                        discount_amount, status, expires_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        cart_id, guest_id, session_id, property_id, room_type_id,
                        rate_plan_id, check_in, check_out, adults, children,
                        pricing["amount_per_night"], pricing["total_before_tax"],
                        pricing["total_after_tax"], Decimal("0"),
                        "ACTIVE", expires_at, now, now,
                    ),
                )
                cart = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Fetch property, room type, and rate plan details for the response
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.name, p.city, p.country,
                       COALESCE(p.hero_image_url, '') AS image_url
                FROM properties p
                WHERE p.property_id = %s
                """,
                (property_id,),
            )
            prop_row = cur.fetchone()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rt.name, rt.description, rt.max_occupancy,
                       COALESCE(rt.image_urls[1], '') AS image_url
                FROM room_types rt
                WHERE rt.room_type_id = %s
                """,
                (room_type_id,),
            )
            rt_row = cur.fetchone()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rp.name, rp.code, rp.cancellation_policy
                FROM rate_plans rp
                WHERE rp.rate_plan_id = %s
                """,
                (rate_plan_id,),
            )
            rp_row = cur.fetchone()

        # Build response matching the frontend Cart interface shape
        response_data = {
            "cart_id": str(cart["cart_id"]),
            "property": {
                "property_id": str(property_id),
                "name": prop_row["name"] if prop_row else "",
                "city": prop_row["city"] if prop_row else "",
                "country": prop_row["country"] if prop_row else "",
                "image_url": prop_row["image_url"] if prop_row else "",
            },
            "room_type": {
                "room_type_id": str(room_type_id),
                "name": rt_row["name"] if rt_row else "",
                "description": rt_row["description"] if rt_row else "",
                "max_occupancy": rt_row["max_occupancy"] if rt_row else 2,
                "image_url": rt_row["image_url"] if rt_row else "",
            },
            "rate_plan": {
                "rate_plan_id": str(rate_plan_id),
                "name": rp_row["name"] if rp_row else "",
                "code": rp_row["code"] if rp_row else "",
                "cancellation_policy": rp_row["cancellation_policy"] if rp_row else "",
            },
            "dates": {
                "check_in": check_in,
                "check_out": check_out,
            },
            "guests": {
                "adults": adults,
                "children": children,
            },
            "pricing": {
                "nightly_rate": float(pricing["amount_per_night"]),
                "number_of_nights": pricing["num_nights"],
                "subtotal": float(pricing["total_before_tax"]),
                "taxes": float(pricing["tax_amount"]),
                "fees": 0,
                "total": float(pricing["total_after_tax"]),
                "currency": "USD",
            },
            "promo_code": None,
            "discount_amount": 0,
        }

        return created(response_data)

    except Exception as e:
        logger.exception("Error creating booking cart")
        return server_error("Failed to create booking cart.")

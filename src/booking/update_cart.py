"""
Lambda handler for PUT /booking/cart/{cartId}.

Updates an existing booking cart with new dates, room type, rate plan,
or guest count. Re-validates availability and recalculates pricing when
relevant fields change. Extends the cart expiration by 30 minutes.

Public endpoint — no authentication required.
"""

import json
from utils.logger import get_logger
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from utils.database import get_conn
from utils.response import ok, bad_request, not_found, server_error, transform_keys
from utils.validation import parse_body, validate_uuid, validate_date, validate_date_range

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


def _calculate_pricing(conn, rate_plan_id, room_type_id, check_in, check_out):
    """
    Calculate pricing for a stay using rate_plan_room_prices and rate_overrides.

    Returns a dict with amount_per_night, total_before_tax, tax_amount,
    total_after_tax, nightly_rates, and num_nights.
    Returns None if rate plan/pricing is not found.
    """
    ci = validate_date(check_in) if isinstance(check_in, str) else check_in
    co = validate_date(check_out) if isinstance(check_out, str) else check_out
    num_nights = (co - ci).days

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rp.discount_type, rp.discount_value, rprp.price_per_night
            FROM rate_plans rp
            JOIN rate_plan_room_prices rprp
                ON rprp.rate_plan_id = rp.rate_plan_id AND rprp.room_type_id = %s
            WHERE rp.rate_plan_id = %s AND rp.is_active = TRUE
            """,
            (room_type_id, rate_plan_id),
        )
        rate_info = cur.fetchone()

    if not rate_info:
        return None

    base_price = Decimal(str(rate_info["price_per_night"]))
    discount_type = rate_info["discount_type"]
    discount_value = Decimal(str(rate_info["discount_value"])) if rate_info["discount_value"] else Decimal("0")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT override_date, override_amount
            FROM rate_overrides
            WHERE rate_plan_id = %s AND room_type_id = %s
              AND override_date >= %s AND override_date < %s
            """,
            (rate_plan_id, room_type_id, check_in, check_out),
        )
        overrides = cur.fetchall()

    override_map = {ov["override_date"].isoformat(): ov["override_amount"] for ov in overrides}

    nightly_rates = []
    total_before_tax = Decimal("0")
    current_date = ci

    while current_date < co:
        date_str = current_date.isoformat()
        night_price = Decimal(str(override_map[date_str])) if date_str in override_map else base_price

        if discount_type == "PERCENTAGE" and discount_value > 0:
            discount_amt = (night_price * discount_value / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            night_price = night_price - discount_amt
        elif discount_type == "FIXED_AMOUNT" and discount_value > 0:
            night_price = max(night_price - discount_value, Decimal("0"))

        night_price = night_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_before_tax += night_price
        nightly_rates.append({"date": date_str, "price": str(night_price)})
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
    """Update an existing booking cart."""
    try:
        # Extract cartId from path
        path_params = event.get("pathParameters") or {}
        cart_id = path_params.get("cartId")
        if not cart_id:
            return bad_request("Missing required path parameter: cartId")
        if not validate_uuid(cart_id):
            return bad_request("Invalid cartId format. Expected UUID.")

        body = parse_body(event)
        if not body:
            return bad_request("Request body is required.")

        conn = get_conn()
        try:
            # Fetch existing cart
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM booking_carts WHERE cart_id = %s",
                    (cart_id,),
                )
                cart = cur.fetchone()

            if not cart:
                conn.commit()
                return not_found("Booking cart not found.")

            if cart["status"] != "ACTIVE":
                conn.commit()
                return bad_request(f"Cart is no longer active. Current status: {cart['status']}")

            now = datetime.now(timezone.utc)
            if cart["expires_at"] < now:
                conn.commit()
                return bad_request("Cart has expired. Please create a new cart.")

            # Determine updated values
            check_in = body.get("checkIn", cart["check_in_date"].isoformat() if isinstance(cart["check_in_date"], date) else cart["check_in_date"])
            check_out = body.get("checkOut", cart["check_out_date"].isoformat() if isinstance(cart["check_out_date"], date) else cart["check_out_date"])
            room_type_id = body.get("roomTypeId", str(cart["room_type_id"]))
            rate_plan_id = body.get("ratePlanId", str(cart["rate_plan_id"]))
            adults = body.get("adults", cart["adults"])
            children = body.get("children", cart["children"])
            property_id = str(cart["property_id"])

            # Validate updated UUIDs
            if "roomTypeId" in body and not validate_uuid(room_type_id):
                conn.commit()
                return bad_request("Invalid roomTypeId format. Expected UUID.")
            if "ratePlanId" in body and not validate_uuid(rate_plan_id):
                conn.commit()
                return bad_request("Invalid ratePlanId format. Expected UUID.")

            # Validate updated dates
            if "checkIn" in body or "checkOut" in body:
                date_error = validate_date_range(check_in, check_out)
                if date_error:
                    conn.commit()
                    return date_error

            ci = validate_date(check_in)
            co = validate_date(check_out)
            num_nights = (co - ci).days

            # Check if dates, room type, or rate plan changed — re-validate
            dates_changed = ("checkIn" in body or "checkOut" in body)
            room_changed = ("roomTypeId" in body)
            rate_changed = ("ratePlanId" in body)
            needs_revalidation = dates_changed or room_changed

            if room_changed:
                # Verify new room type exists
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT room_type_id FROM room_types
                        WHERE room_type_id = %s AND property_id = %s AND is_active = TRUE
                        """,
                        (room_type_id, property_id),
                    )
                    if not cur.fetchone():
                        conn.commit()
                        return not_found("Room type not found or not available at this property.")

            if rate_changed:
                # Verify new rate plan exists
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

            if needs_revalidation:
                # Re-validate availability
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
                    return bad_request("Room type is not available for the updated date range.")

            # Recalculate pricing
            pricing = _calculate_pricing(conn, rate_plan_id, room_type_id, check_in, check_out)
            if pricing is None:
                conn.commit()
                return bad_request("Unable to calculate pricing for the selected rate plan and room type.")

            # If there was a promo discount, recalculate total_after_tax with it
            discount_amount = Decimal(str(cart["discount_amount"])) if cart["discount_amount"] else Decimal("0")
            adjusted_total_before_tax = pricing["total_before_tax"] - discount_amount
            if adjusted_total_before_tax < 0:
                adjusted_total_before_tax = Decimal("0")
            adjusted_tax = (adjusted_total_before_tax * TAX_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            adjusted_total_after_tax = adjusted_total_before_tax + adjusted_tax

            # Extend expiration
            new_expires_at = now + timedelta(minutes=30)

            # Update the cart
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE booking_carts SET
                        room_type_id = %s,
                        rate_plan_id = %s,
                        check_in_date = %s,
                        check_out_date = %s,
                        adults = %s,
                        children = %s,
                        amount_per_night = %s,
                        total_before_tax = %s,
                        total_after_tax = %s,
                        expires_at = %s,
                        updated_at = %s
                    WHERE cart_id = %s
                    RETURNING *
                    """,
                    (
                        room_type_id, rate_plan_id, check_in, check_out,
                        adults, children,
                        pricing["amount_per_night"], pricing["total_before_tax"],
                        adjusted_total_after_tax, new_expires_at, now,
                        cart_id,
                    ),
                )
                updated_cart = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(updated_cart)
        serialized["pricing"] = {
            "nightly_rates": pricing["nightly_rates"],
            "num_nights": pricing["num_nights"],
            "amount_per_night": str(pricing["amount_per_night"]),
            "total_before_tax": str(pricing["total_before_tax"]),
            "tax_rate": str(TAX_RATE),
            "tax_amount": str(pricing["tax_amount"]),
            "total_after_tax": str(adjusted_total_after_tax),
            "discount_amount": str(discount_amount),
            "currency": "USD",
        }

        return ok(serialized)

    except Exception as e:
        logger.exception("Error updating booking cart")
        return server_error("Failed to update booking cart.")

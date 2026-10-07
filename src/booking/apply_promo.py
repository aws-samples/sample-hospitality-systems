"""
Lambda handler for POST /booking/cart/{cartId}/promo.

Validates and applies a promotional code to an existing booking cart.
Checks promo eligibility (active status, date validity, usage limits,
minimum stay, minimum amount, and property restrictions) before applying
the discount to the cart total.

Public endpoint — no authentication required.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, not_found, ok, server_error
from utils.validation import parse_body, require_fields, validate_uuid

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


def handler(event, context):
    """Apply a promo code to a booking cart."""
    try:
        # Extract cartId from path
        path_params = event.get("pathParameters") or {}
        cart_id = path_params.get("cartId")
        if not cart_id:
            return bad_request("Missing required path parameter: cartId")
        if not validate_uuid(cart_id):
            return bad_request("Invalid cartId format. Expected UUID.")

        body = parse_body(event)
        field_error = require_fields(body, ["promoCode"])
        if field_error:
            return field_error

        promo_code = body["promoCode"]

        conn = get_conn()
        try:
            # Fetch cart
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

            now = datetime.now(UTC)
            if cart["expires_at"] < now:
                conn.commit()
                return bad_request("Cart has expired. Please create a new cart.")

            # Look up promo code (case insensitive)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM promo_codes
                    WHERE LOWER(code) = LOWER(%s)
                      AND is_active = TRUE
                    """,
                    (promo_code,),
                )
                promo = cur.fetchone()

            if not promo:
                conn.commit()
                return bad_request("Invalid or inactive promo code.")

            today = date.today()

            # Validate date range
            if promo["valid_from"] and promo["valid_from"] > today:
                conn.commit()
                return bad_request("Promo code is not yet valid.")

            if promo["valid_to"] and promo["valid_to"] < today:
                conn.commit()
                return bad_request("Promo code has expired.")

            # Validate usage limits
            if promo["max_uses"] is not None and promo["used_count"] >= promo["max_uses"]:
                conn.commit()
                return bad_request("Promo code has reached its maximum usage limit.")

            # Calculate number of nights
            check_in = cart["check_in_date"]
            check_out = cart["check_out_date"]
            if isinstance(check_in, str):
                check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
            if isinstance(check_out, str):
                check_out = datetime.strptime(check_out, "%Y-%m-%d").date()
            num_nights = (check_out - check_in).days

            # Validate minimum stay nights
            min_stay = promo["min_stay_nights"] or 1
            if num_nights < min_stay:
                conn.commit()
                return bad_request(
                    f"Promo code requires a minimum stay of {min_stay} nights. "
                    f"Your booking is for {num_nights} nights."
                )

            # Validate minimum booking amount
            total_before_tax = Decimal(str(cart["total_before_tax"]))
            min_amount = Decimal(str(promo["min_booking_amount"])) if promo["min_booking_amount"] else Decimal("0")
            if total_before_tax < min_amount:
                conn.commit()
                return bad_request(
                    f"Promo code requires a minimum booking amount of ${min_amount}. "
                    f"Your booking total is ${total_before_tax}."
                )

            # Validate applicable properties
            applicable_properties = promo["applicable_properties"]
            if applicable_properties and len(applicable_properties) > 0:
                property_id = str(cart["property_id"])
                applicable_strs = [str(p) for p in applicable_properties]
                if property_id not in applicable_strs:
                    conn.commit()
                    return bad_request("Promo code is not valid for this property.")

            # Calculate discount
            discount_type = promo["discount_type"]
            discount_value = Decimal(str(promo["discount_value"])) if promo["discount_value"] else Decimal("0")

            if discount_type == "PERCENTAGE":
                discount_amount = (total_before_tax * discount_value / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            elif discount_type == "FIXED_AMOUNT":
                discount_amount = discount_value
            else:
                discount_amount = Decimal("0")

            # Cap discount at total_before_tax
            if discount_amount > total_before_tax:
                discount_amount = total_before_tax

            discount_amount = discount_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Recalculate totals
            adjusted_total_before_tax = total_before_tax - discount_amount
            tax_amount = (adjusted_total_before_tax * TAX_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            new_total_after_tax = adjusted_total_before_tax + tax_amount

            # Update cart with promo code and discount
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE booking_carts SET
                        promo_code = %s,
                        discount_amount = %s,
                        total_after_tax = %s,
                        updated_at = %s
                    WHERE cart_id = %s
                    RETURNING *
                    """,
                    (
                        promo["code"],
                        discount_amount,
                        new_total_after_tax,
                        now,
                        cart_id,
                    ),
                )
                updated_cart = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(updated_cart)
        serialized["promo_details"] = {
            "code": promo["code"],
            "description": promo["description"],
            "discount_type": discount_type,
            "discount_value": str(discount_value),
            "discount_amount": str(discount_amount),
            "total_before_discount": str(total_before_tax),
            "total_after_discount": str(adjusted_total_before_tax),
            "tax_amount": str(tax_amount),
            "total_after_tax": str(new_total_after_tax),
        }

        return ok(serialized)

    except Exception:
        logger.exception("Error applying promo code")
        return server_error("Failed to apply promo code.")

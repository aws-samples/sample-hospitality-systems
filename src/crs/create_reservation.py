"""
Lambda handler for POST /reservations.

Creates a new reservation after validating availability, calculating pricing
from rate plan room prices, and generating a confirmation number. Decrements
available inventory for each date in the range and publishes a
reservation.created event.
"""

import secrets
import string
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from utils.auth import get_guest_id
from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.response import (
    bad_request,
    created,
    not_found,
    server_error,
)
from utils.validation import (
    parse_body,
    require_fields,
    validate_date,
    validate_date_range,
    validate_uuid,
)

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


def _generate_confirmation_number():
    """Generate a confirmation number in format RES-XXXXXX."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"RES-{random_part}"


def _get_guest_id_from_sub(conn, cognito_sub):
    """Look up the guest_id from the cognito_sub claim."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT guest_id FROM guests WHERE cognito_sub = %s",
            (cognito_sub,),
        )
        row = cur.fetchone()
    if row:
        return row["guest_id"]
    return None


def handler(event, context):
    """Create a new reservation."""
    try:
        # Auth required
        try:
            cognito_sub = get_guest_id(event)
        except (KeyError, TypeError):
            return bad_request("Authentication is required.")

        body = parse_body(event)
        required = [
            "propertyId", "roomTypeId", "ratePlanId",
            "checkInDate", "checkOutDate", "adults",
        ]
        field_error = require_fields(body, required)
        if field_error:
            return field_error

        property_id = body["propertyId"]
        room_type_id = body["roomTypeId"]
        rate_plan_id = body["ratePlanId"]
        check_in_date = body["checkInDate"]
        check_out_date = body["checkOutDate"]
        adults = body.get("adults", 1)
        children = body.get("children", 0)
        guest_info = body.get("guestInfo", {})
        payment_method_id = body.get("paymentMethodId")
        additional_notes = body.get("additionalNotes")

        # Validate UUIDs
        for field_name, field_val in [
            ("propertyId", property_id),
            ("roomTypeId", room_type_id),
            ("ratePlanId", rate_plan_id),
        ]:
            if not validate_uuid(field_val):
                return bad_request(f"{field_name} must be a valid UUID.")

        # Validate dates
        date_error = validate_date_range(check_in_date, check_out_date)
        if date_error:
            return date_error

        ci_date = validate_date(check_in_date)
        co_date = validate_date(check_out_date)
        num_nights = (co_date - ci_date).days

        try:
            adults = int(adults)
            children = int(children)
        except (ValueError, TypeError):
            return bad_request("adults and children must be valid integers.")

        conn = get_conn()
        try:
            # Look up guest_id from cognito_sub
            guest_id = _get_guest_id_from_sub(conn, cognito_sub)
            if not guest_id:
                conn.rollback()
                return bad_request("Guest profile not found. Please complete registration first.")

            # Validate room type exists and meets occupancy
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT room_type_id, name, max_occupancy, base_rate
                    FROM room_types
                    WHERE room_type_id = %s AND property_id = %s AND is_active = TRUE
                    """,
                    (room_type_id, property_id),
                )
                room_type = cur.fetchone()

            if not room_type:
                conn.rollback()
                return not_found("Room type not found or inactive.")

            if room_type["max_occupancy"] < adults + children:
                conn.rollback()
                return bad_request(
                    f"Room type max occupancy is {room_type['max_occupancy']}. "
                    f"Requested: {adults + children} guests."
                )

            # Validate rate plan and get pricing
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rp.rate_plan_id, rp.name AS rate_plan_name,
                           rp.cancellation_policy, rp.currency,
                           rp_prices.base_price
                    FROM rate_plan_room_prices rp_prices
                    JOIN rate_plans rp ON rp.rate_plan_id = rp_prices.rate_plan_id
                    WHERE rp_prices.rate_plan_id = %s
                      AND rp_prices.room_type_id = %s
                      AND rp.is_active = TRUE
                    """,
                    (rate_plan_id, room_type_id),
                )
                rate_plan = cur.fetchone()

            if not rate_plan:
                conn.rollback()
                return not_found("Rate plan not found or not available for this room type.")

            # Check availability for all dates in range
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT inventory_date, total_inventory, sold
                    FROM room_inventory
                    WHERE room_type_id = %s
                      AND inventory_date >= %s
                      AND inventory_date < %s
                    ORDER BY inventory_date
                    """,
                    (room_type_id, ci_date, co_date),
                )
                inventory_rows = cur.fetchall()

            if len(inventory_rows) < num_nights:
                conn.rollback()
                return bad_request("Inventory not available for all dates in the requested range.")

            for inv in inventory_rows:
                if inv["total_inventory"] - inv["sold"] < 1:
                    conn.rollback()
                    return bad_request(
                        f"No availability on {inv['inventory_date']}."
                    )

            # Calculate pricing
            nightly_rate = Decimal(str(rate_plan["base_price"]))
            room_total = nightly_rate * num_nights
            tax_rate = Decimal("0.12")
            tax_amount = (room_total * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_amount = room_total + tax_amount

            # Generate confirmation number
            confirmation_number = _generate_confirmation_number()
            reservation_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            # Snapshot rate plan and room type names
            booked_room_type_name = room_type["name"]
            booked_rate_plan_name = rate_plan["rate_plan_name"]
            booked_rate_plan_code = str(rate_plan["rate_plan_id"])
            cancellation_policy = rate_plan["cancellation_policy"]
            currency = rate_plan["currency"]

            # INSERT reservation
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reservations (
                        reservation_id, confirmation_number, property_id,
                        guest_id, room_type_id, rate_plan_id,
                        check_in_date, check_out_date, num_nights,
                        adults, children, status,
                        booked_room_type_name, booked_rate_plan_name,
                        booked_rate_plan_code, cancellation_policy,
                        nightly_rate, room_total, tax_amount, total_amount,
                        currency, payment_method_id, additional_notes,
                        guest_info, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, 'CONFIRMED',
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        reservation_id, confirmation_number, property_id,
                        str(guest_id), room_type_id, rate_plan_id,
                        ci_date, co_date, num_nights,
                        adults, children,
                        booked_room_type_name, booked_rate_plan_name,
                        booked_rate_plan_code, cancellation_policy,
                        str(nightly_rate), str(room_total), str(tax_amount), str(total_amount),
                        currency, payment_method_id, additional_notes,
                        __import__("json").dumps(guest_info),
                        now, now,
                    ),
                )
                reservation = cur.fetchone()

            # Update availability (increment sold for each date)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE room_inventory
                    SET sold = sold + 1, updated_at = %s
                    WHERE room_type_id = %s
                      AND inventory_date >= %s
                      AND inventory_date < %s
                    """,
                    (now, room_type_id, ci_date, co_date),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(reservation)

        # Publish reservation.created event using the shared camelCase schema
        # (consumed by PMS billing, housekeeping, and notifications services).
        try:
            publish_event(
                source="anycompany.reservations",
                detail_type="reservation.created",
                detail={
                    "reservationId": reservation_id,
                    "confirmationNumber": confirmation_number,
                    "propertyId": property_id,
                    "guestId": str(guest_id),
                    "roomTypeId": room_type_id,
                    "ratePlanId": rate_plan_id,
                    "checkInDate": check_in_date,
                    "checkOutDate": check_out_date,
                    "totalAfterTax": str(total_amount),
                    "currency": currency,
                    "status": "CONFIRMED",
                },
            )
        except Exception as e:
            logger.warning("Failed to publish reservation.created event", error=str(e))

        return created(serialized)

    except Exception:
        logger.exception("Error creating reservation")
        return server_error("Failed to create reservation.")

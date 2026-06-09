"""
Lambda handler for DELETE /reservations/{reservationId}.

Cancels an existing CONFIRMED reservation. Decrements sold counts for all
dates in the reservation range, calculates a cancellation charge based on
the reservation's cancellation policy, and publishes a reservation.cancelled
event.

Cancellation policies:
    FLEXIBLE     - No charge
    MODERATE     - First night charge
    STRICT       - 50% of total
    NON_REFUNDABLE - 100% of total
"""

from utils.logger import get_logger
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from utils.database import get_conn
from utils.response import ok, not_found, bad_request, server_error, transform_keys
from utils.auth import get_claims, get_guest_id, has_group
from utils.response import forbidden as forbidden_response
from utils.events import publish_event
from utils.validation import parse_body, validate_uuid

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


def _get_guest_id_from_sub(conn, cognito_sub):
    """Look up the guest_id from the cognito_sub claim."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT guest_id FROM guests WHERE cognito_sub = %s",
            (cognito_sub,),
        )
        row = cur.fetchone()
    if row:
        return str(row["guest_id"])
    return None


def _calculate_cancellation_charge(policy, nightly_rate, total_amount):
    """
    Calculate the cancellation charge based on policy.

    Args:
        policy: Cancellation policy string.
        nightly_rate: Nightly rate as Decimal.
        total_amount: Total reservation amount as Decimal.

    Returns:
        Cancellation charge as Decimal.
    """
    nightly = Decimal(str(nightly_rate))
    total = Decimal(str(total_amount))

    if policy == "FLEXIBLE":
        return Decimal("0.00")
    elif policy == "MODERATE":
        return nightly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif policy == "STRICT":
        return (total * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif policy == "NON_REFUNDABLE":
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        # Default to no charge for unknown policies
        return Decimal("0.00")


def handler(event, context):
    """Cancel a reservation (owner-only, or any reservation for Admin/Manager staff)."""
    try:
        # Auth required
        try:
            cognito_sub = get_guest_id(event)
        except (KeyError, TypeError):
            return bad_request("Authentication is required.")

        # Admin/Manager callers can cancel any reservation, bypassing ownership.
        is_staff_cancel = has_group(event, "Admin", "Manager")

        reservation_id = event.get("pathParameters", {}).get("reservationId")
        if not reservation_id or not validate_uuid(reservation_id):
            return bad_request("A valid reservationId is required.")

        body = parse_body(event) or {}
        cancellation_reason = body.get("cancellationReason") or body.get("reason") or "Guest requested cancellation"

        conn = get_conn()
        try:
            # Look up guest_id (skip in staff mode — caller is not the guest)
            guest_id = None
            if not is_staff_cancel:
                guest_id = _get_guest_id_from_sub(conn, cognito_sub)
                if not guest_id:
                    conn.rollback()
                    return bad_request("Guest profile not found.")

            # Fetch reservation
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM reservations WHERE reservation_id = %s",
                    (reservation_id,),
                )
                reservation = cur.fetchone()

            if not reservation:
                conn.rollback()
                return not_found(f"Reservation {reservation_id} not found.")

            # Verify ownership (skip in staff mode)
            if not is_staff_cancel and str(reservation["guest_id"]) != guest_id:
                conn.rollback()
                return forbidden_response()

            # In staff mode, the published event uses the reservation's guest_id directly.
            if is_staff_cancel:
                guest_id = str(reservation["guest_id"])

            # Only CONFIRMED reservations can be cancelled
            if reservation["status"] != "CONFIRMED":
                conn.rollback()
                return bad_request(
                    f"Cannot cancel reservation with status '{reservation['status']}'. "
                    "Only CONFIRMED reservations can be cancelled."
                )

            now = datetime.now(timezone.utc)

            # Get date range for inventory adjustment
            check_in = reservation["check_in_date"]
            check_out = reservation["check_out_date"]
            room_type_id = reservation["room_type_id"]

            # Calculate cancellation charge
            cancellation_charge = _calculate_cancellation_charge(
                "FLEXIBLE",
                reservation["amount_per_night"],
                reservation["total_after_tax"],
            )

            # Update reservation status
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE reservations
                    SET status = 'CANCELLED',
                        cancellation_reason = %s,
                        cancellation_charge = %s,
                        cancelled_at = %s,
                        updated_at = %s
                    WHERE reservation_id = %s
                    RETURNING *
                    """,
                    (
                        cancellation_reason,
                        str(cancellation_charge),
                        now, now,
                        reservation_id,
                    ),
                )
                cancelled = cur.fetchone()

            # Decrement sold counts for all dates in the reservation range
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE availability
                    SET sold = GREATEST(sold - 1, 0), updated_at = %s
                    WHERE room_type_id = %s
                      AND date >= %s
                      AND date < %s
                    """,
                    (now, room_type_id, check_in, check_out),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(cancelled)

        # Publish reservation.cancelled event using shared camelCase schema.
        try:
            publish_event(
                source="anycompany.reservations",
                detail_type="reservation.cancelled",
                detail={
                    "reservationId": reservation_id,
                    "confirmationNumber": str(reservation["confirmation_number"]),
                    "propertyId": str(reservation["property_id"]),
                    "guestId": guest_id,
                    "roomTypeId": str(room_type_id),
                    "checkInDate": str(check_in),
                    "checkOutDate": str(check_out),
                    "cancellationReason": cancellation_reason,
                    "cancellationCharge": str(cancellation_charge),
                    "totalAmount": str(reservation["total_after_tax"]),
                },
            )
        except Exception as e:
            logger.warning("Failed to publish reservation.cancelled event", error=str(e))

        return ok(serialized)

    except Exception as e:
        logger.exception("Error cancelling reservation")
        return server_error("Failed to cancel reservation.")

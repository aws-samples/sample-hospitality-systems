"""
Lambda handler for PUT /reservations/{reservationId}.

Updates an existing reservation. Only certain fields are allowed to be
modified: check_in_date, check_out_date, adults, children, additional_notes.
If dates change, availability is revalidated and sold counts are adjusted
(decrement old date range, increment new date range). Pricing is
recalculated when dates change.
"""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from utils.auth import get_guest_id
from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.response import bad_request, not_found, ok, server_error
from utils.response import forbidden as forbidden_response
from utils.validation import (
    parse_body,
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


def handler(event, context):
    """Update an existing reservation (owner-only)."""
    try:
        # Auth required
        try:
            cognito_sub = get_guest_id(event)
        except (KeyError, TypeError):
            return bad_request("Authentication is required.")

        reservation_id = event.get("pathParameters", {}).get("reservationId")
        if not reservation_id or not validate_uuid(reservation_id):
            return bad_request("A valid reservationId is required.")

        body = parse_body(event)
        if not body:
            return bad_request("Request body is required.")

        conn = get_conn()
        try:
            # Look up guest_id
            guest_id = _get_guest_id_from_sub(conn, cognito_sub)
            if not guest_id:
                conn.rollback()
                return bad_request("Guest profile not found.")

            # Fetch existing reservation
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM reservations WHERE reservation_id = %s",
                    (reservation_id,),
                )
                reservation = cur.fetchone()

            if not reservation:
                conn.rollback()
                return not_found(f"Reservation {reservation_id} not found.")

            # Verify ownership
            if str(reservation["guest_id"]) != guest_id:
                conn.rollback()
                return forbidden_response()

            # Only CONFIRMED reservations can be updated
            if reservation["status"] != "CONFIRMED":
                conn.rollback()
                return bad_request(
                    f"Cannot update reservation with status '{reservation['status']}'. "
                    "Only CONFIRMED reservations can be updated."
                )

            # Extract allowed update fields
            new_check_in = body.get("checkInDate")
            new_check_out = body.get("checkOutDate")
            new_adults = body.get("adults")
            new_children = body.get("children")
            new_notes = body.get("additionalNotes")

            # Determine effective dates
            old_ci = reservation["check_in_date"]
            old_co = reservation["check_out_date"]
            # Convert to date objects if they are strings
            if isinstance(old_ci, str):
                old_ci = validate_date(old_ci)
            if isinstance(old_co, str):
                old_co = validate_date(old_co)

            eff_ci = old_ci
            eff_co = old_co
            dates_changed = False

            if new_check_in or new_check_out:
                ci_str = new_check_in or str(old_ci)
                co_str = new_check_out or str(old_co)

                date_error = validate_date_range(ci_str, co_str)
                if date_error:
                    conn.rollback()
                    return date_error

                eff_ci = validate_date(ci_str)
                eff_co = validate_date(co_str)

                if eff_ci != old_ci or eff_co != old_co:
                    dates_changed = True

            eff_adults = int(new_adults) if new_adults is not None else reservation["adults"]
            eff_children = int(new_children) if new_children is not None else reservation["children"]

            now = datetime.now(UTC)
            room_type_id = reservation["room_type_id"]

            if dates_changed:
                num_nights = (eff_co - eff_ci).days

                # Check availability for new dates (exclude current reservation's sold count)
                # First decrement old dates
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE room_inventory
                        SET sold = sold - 1, updated_at = %s
                        WHERE room_type_id = %s
                          AND inventory_date >= %s
                          AND inventory_date < %s
                        """,
                        (now, room_type_id, old_ci, old_co),
                    )

                # Check new date availability
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
                        (room_type_id, eff_ci, eff_co),
                    )
                    inventory_rows = cur.fetchall()

                if len(inventory_rows) < num_nights:
                    # Rollback decrement
                    conn.rollback()
                    return bad_request("Inventory not available for all dates in the new range.")

                for inv in inventory_rows:
                    if inv["total_inventory"] - inv["sold"] < 1:
                        conn.rollback()
                        return bad_request(
                            f"No availability on {inv['inventory_date']} for the new date range."
                        )

                # Increment sold for new dates
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE room_inventory
                        SET sold = sold + 1, updated_at = %s
                        WHERE room_type_id = %s
                          AND inventory_date >= %s
                          AND inventory_date < %s
                        """,
                        (now, room_type_id, eff_ci, eff_co),
                    )

                # Recalculate pricing
                nightly_rate = Decimal(str(reservation["nightly_rate"]))
                room_total = nightly_rate * num_nights
                tax_rate = Decimal("0.12")
                tax_amount = (room_total * tax_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total_amount = room_total + tax_amount

                # Update reservation with new dates and pricing
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE reservations
                        SET check_in_date = %s,
                            check_out_date = %s,
                            num_nights = %s,
                            adults = %s,
                            children = %s,
                            additional_notes = COALESCE(%s, additional_notes),
                            room_total = %s,
                            tax_amount = %s,
                            total_amount = %s,
                            updated_at = %s
                        WHERE reservation_id = %s
                        RETURNING *
                        """,
                        (
                            eff_ci, eff_co, num_nights,
                            eff_adults, eff_children,
                            new_notes,
                            str(room_total), str(tax_amount), str(total_amount),
                            now, reservation_id,
                        ),
                    )
                    updated = cur.fetchone()
            else:
                # No date change, just update allowed fields
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE reservations
                        SET adults = %s,
                            children = %s,
                            additional_notes = COALESCE(%s, additional_notes),
                            updated_at = %s
                        WHERE reservation_id = %s
                        RETURNING *
                        """,
                        (
                            eff_adults, eff_children,
                            new_notes, now, reservation_id,
                        ),
                    )
                    updated = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(updated)

        # Publish reservation.modified event using shared camelCase schema.
        # Name matches what PMS billing consumer expects (process_event.py).
        try:
            modified_detail = {
                "reservationId": reservation_id,
                "propertyId": str(reservation["property_id"]),
                "guestId": guest_id,
                "datesChanged": dates_changed,
                "checkInDate": str(eff_ci),
                "checkOutDate": str(eff_co),
                "status": "CONFIRMED",
            }
            # Include new totalAmount only when dates changed (used by folio recalc)
            if dates_changed:
                modified_detail["totalAmount"] = str(total_amount)
            publish_event(
                source="anycompany.reservations",
                detail_type="reservation.modified",
                detail=modified_detail,
            )
        except Exception as e:
            logger.warning("Failed to publish reservation.modified event", error=str(e))

        return ok(serialized)

    except Exception:
        logger.exception("Error updating reservation")
        return server_error("Failed to update reservation.")

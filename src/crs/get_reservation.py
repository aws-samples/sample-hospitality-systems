"""
Lambda handler for GET /reservations/{reservationId}.

Retrieves a single reservation by ID. Requires authentication and
verifies that the requesting guest owns the reservation.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.auth import get_guest_id
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, forbidden, not_found, ok, server_error
from utils.validation import validate_uuid

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


def handler(event, context):
    """Get a single reservation by ID (owner-only)."""
    try:
        try:
            cognito_sub = get_guest_id(event)
        except (KeyError, TypeError):
            return bad_request("Authentication is required.")

        reservation_id = event.get("pathParameters", {}).get("reservationId")
        if not reservation_id or not validate_uuid(reservation_id):
            return bad_request("A valid reservationId is required.")

        conn = get_conn()
        try:
            guest_id = _get_guest_id_from_sub(conn, cognito_sub)
            if not guest_id:
                conn.commit()
                return bad_request("Guest profile not found.")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.*,
                           p.name AS property_name,
                           rt.name AS room_type_name,
                           r.total_after_tax AS total_amount,
                           r.currency_code AS currency
                    FROM reservations r
                    LEFT JOIN properties p ON p.property_id = r.property_id
                    LEFT JOIN room_types rt ON rt.room_type_id = r.room_type_id
                    WHERE r.reservation_id = %s
                    """,
                    (reservation_id,),
                )
                reservation = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not reservation:
            return not_found(f"Reservation {reservation_id} not found.")

        if str(reservation["guest_id"]) != guest_id:
            return forbidden()

        return ok(_serialize_row(reservation))

    except Exception:
        logger.exception("Error getting reservation")
        return server_error("Failed to get reservation.")

"""
PMS Room Change Handler.

PUT /stays/{stayId}/room
Move a checked-in guest to a different room.
"""

from utils.auth import get_user_id
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, verify_property_access
from utils.validation import parse_body, validate_uuid

logger = get_logger("pms-checkinout")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")
        staff_user_id = get_user_id(event)

        reservation_id = validate_uuid(
            event.get("pathParameters", {}).get("reservationId"), "reservationId"
        )

        body = parse_body(event)
        if not body or not body.get("newRoomId"):
            return error(400, "VALIDATION_ERROR", "newRoomId is required")

        new_room_id = validate_uuid(body["newRoomId"], "newRoomId")
        reason = body.get("reason", "")
        if reason and len(reason) > 2000:
            return error(400, "VALIDATION_ERROR", "reason must be 2000 characters or less")

        with get_conn() as conn, conn.cursor() as cur:
            # Get current reservation
            cur.execute(
                "SELECT reservation_id, property_id, guest_id, room_id, status "
                "FROM reservations WHERE reservation_id = %s",
                [reservation_id],
            )
            reservation = cur.fetchone()
            if not reservation:
                return error(404, "NOT_FOUND", "Stay not found")

            verify_property_access(event, str(reservation["property_id"]))

            if reservation["status"] != "CHECKED_IN":
                return error(409, "INVALID_STATE", "Guest must be CHECKED_IN for room change")

            old_room_id = reservation["room_id"]
            if str(old_room_id) == new_room_id:
                return error(400, "VALIDATION_ERROR", "New room is the same as current room")

            # Verify new room is available
            cur.execute(
                "SELECT room_id, room_number, room_type_id, status FROM rooms WHERE room_id = %s",
                [new_room_id],
            )
            new_room = cur.fetchone()
            if not new_room:
                return error(404, "NOT_FOUND", "New room not found")
            if new_room["status"] != "AVAILABLE":
                return error(409, "ROOM_NOT_AVAILABLE", f"Room {new_room['room_number']} is not available")

            # Get old room number for logging
            cur.execute("SELECT room_number FROM rooms WHERE room_id = %s", [old_room_id])
            old_room = cur.fetchone()
            old_room_number = old_room["room_number"] if old_room else ""

            # Execute room change
            cur.execute(
                "UPDATE reservations SET room_id = %s, updated_at = now() WHERE reservation_id = %s",
                [new_room_id, reservation_id],
            )
            cur.execute(
                "UPDATE rooms SET status = 'DIRTY', updated_at = now() WHERE room_id = %s",
                [old_room_id],
            )
            cur.execute(
                "UPDATE rooms SET status = 'OCCUPIED', updated_at = now() WHERE room_id = %s",
                [new_room_id],
            )

            # Log the change
            cur.execute(
                "INSERT INTO checkinout_records "
                "(reservation_id, property_id, guest_id, room_id, room_number, "
                "record_type, performed_by, notes) "
                "VALUES (%s, %s, %s, %s, %s, 'CHECKIN', %s, %s)",
                [
                    reservation_id, reservation["property_id"],
                    reservation["guest_id"], new_room_id,
                    new_room["room_number"], staff_user_id,
                    f"Room change: {old_room_number} → {new_room['room_number']}. {reason}".strip(),
                ],
            )
            conn.commit()

        return ok({
            "reservationId": reservation_id,
            "previousRoom": old_room_number,
            "newRoom": new_room["room_number"],
            "newRoomId": new_room_id,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error during room change")
        return server_error()

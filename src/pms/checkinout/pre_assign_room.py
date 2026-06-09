"""
PMS Pre-Assign Room Handler.

PUT /stays/{reservationId}/assign-room
Pre-assign a specific room to a reservation before arrival (VIP handling).
"""

from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid, parse_body
from utils.tenant import require_groups, verify_property_access, ForbiddenError

logger = get_logger("pms-checkinout")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin")

        reservation_id = validate_uuid(
            event.get("pathParameters", {}).get("reservationId"), "reservationId"
        )

        body = parse_body(event)
        if not body or not body.get("roomId"):
            return error(400, "VALIDATION_ERROR", "roomId is required")

        room_id = validate_uuid(body["roomId"], "roomId")

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get reservation
                cur.execute(
                    "SELECT reservation_id, property_id, room_type_id, room_id, status "
                    "FROM reservations WHERE reservation_id = %s",
                    [reservation_id],
                )
                reservation = cur.fetchone()
                if not reservation:
                    return error(404, "NOT_FOUND", "Reservation not found")

                verify_property_access(event, str(reservation["property_id"]))

                if reservation["status"] != "CONFIRMED":
                    return error(409, "INVALID_STATE", "Can only pre-assign rooms to CONFIRMED reservations")

                if reservation["room_id"]:
                    return error(409, "ALREADY_ASSIGNED", "Room already assigned to this reservation")

                # Verify room exists, is available, and matches type
                cur.execute(
                    "SELECT r.room_id, r.room_number, r.room_type_id, r.status, "
                    "rt.name AS room_type_name "
                    "FROM rooms r "
                    "LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id "
                    "WHERE r.room_id = %s AND r.property_id = %s",
                    [room_id, reservation["property_id"]],
                )
                room = cur.fetchone()
                if not room:
                    return error(404, "NOT_FOUND", "Room not found in this property")

                if room["status"] != "AVAILABLE":
                    return error(409, "ROOM_NOT_AVAILABLE", f"Room {room['room_number']} is not available")

                if str(room["room_type_id"]) != str(reservation["room_type_id"]):
                    logger.info("Room type mismatch (Manager override allowed)",
                               room_type_id=str(room["room_type_id"]),
                               reservation_type_id=str(reservation["room_type_id"]))

                # Assign room
                cur.execute(
                    "UPDATE reservations SET room_id = %s, updated_at = now() "
                    "WHERE reservation_id = %s",
                    [room_id, reservation_id],
                )
                conn.commit()

        return ok({
            "reservationId": reservation_id,
            "roomId": room_id,
            "roomNumber": room["room_number"],
            "roomType": room["room_type_name"],
            "status": "PRE_ASSIGNED",
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error pre-assigning room")
        return server_error()

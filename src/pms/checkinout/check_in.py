"""
PMS Check-In Handler.

POST /stays/{reservationId}/checkin
Assigns a room, updates reservation status, advances Step Functions lifecycle.
"""

import json
import os
from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid, parse_body
from utils.events import publish_event
from utils.tenant import require_groups, verify_property_access, ForbiddenError
from utils.auth import get_user_id

logger = get_logger("pms-checkinout")

SFN_CLIENT = None


def get_sfn_client():
    global SFN_CLIENT
    if SFN_CLIENT is None:
        import boto3
        SFN_CLIENT = boto3.client("stepfunctions")
    return SFN_CLIENT


@logger.inject_lambda_context
def handler(event, context):
    try:
        # Auth
        require_groups(event, "FrontDesk", "Manager", "Admin")
        staff_user_id = get_user_id(event)

        # Validate input
        reservation_id = validate_uuid(
            event.get("pathParameters", {}).get("reservationId"), "reservationId"
        )
        body = parse_body(event) or {}
        requested_room_id = body.get("roomId")
        notes = body.get("notes", "")
        if notes and len(notes) > 2000:
            return error(400, "VALIDATION_ERROR", "Notes must be 2000 characters or less")

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Load reservation
                cur.execute(
                    "SELECT reservation_id, property_id, guest_id, room_type_id, room_id, "
                    "status, check_in_task_token FROM reservations WHERE reservation_id = %s",
                    [reservation_id],
                )
                reservation = cur.fetchone()
                if not reservation:
                    return error(404, "NOT_FOUND", "Reservation not found")

                # Tenant isolation
                verify_property_access(event, str(reservation["property_id"]))

                # Validate state
                if reservation["status"] != "CONFIRMED":
                    return error(
                        409, "INVALID_STATE",
                        f"Reservation must be CONFIRMED for check-in, current: {reservation['status']}"
                    )

                # Room assignment
                if requested_room_id:
                    room = _get_specific_room(cur, requested_room_id)
                else:
                    room = _find_available_room(cur, reservation["property_id"], reservation["room_type_id"])

                if not room:
                    return error(409, "NO_ROOM_AVAILABLE", "No available room of the requested type")

                if room["status"] != "AVAILABLE":
                    return error(409, "ROOM_NOT_AVAILABLE", f"Room {room['room_number']} is not available")

                # Execute check-in (all in one transaction)
                cur.execute(
                    "UPDATE reservations SET status = 'CHECKED_IN', room_id = %s, "
                    "checked_in_at = now(), updated_at = now() WHERE reservation_id = %s",
                    [room["room_id"], reservation_id],
                )
                cur.execute(
                    "UPDATE rooms SET status = 'OCCUPIED', updated_at = now() WHERE room_id = %s",
                    [room["room_id"]],
                )
                cur.execute(
                    "INSERT INTO checkinout_records "
                    "(reservation_id, property_id, guest_id, room_id, room_number, "
                    "record_type, performed_by, notes) "
                    "VALUES (%s, %s, %s, %s, %s, 'CHECKIN', %s, %s)",
                    [
                        reservation_id, reservation["property_id"],
                        reservation["guest_id"], room["room_id"],
                        room["room_number"], staff_user_id, notes or None,
                    ],
                )
                conn.commit()

        # Advance Step Functions (outside transaction)
        if reservation.get("check_in_task_token"):
            try:
                get_sfn_client().send_task_success(
                    taskToken=reservation["check_in_task_token"],
                    output=json.dumps({"status": "CHECKED_IN", "roomId": str(room["room_id"])}),
                )
            except Exception as e:
                logger.warning("Failed to advance SFN", error=str(e))

        # Publish event (EVENT_BUS_NAME is read from env inside publish_event)
        try:
            publish_event(
                source="anycompany.pms",
                detail_type="checkinout.checked_in",
                detail={
                    "reservationId": reservation_id,
                    "propertyId": str(reservation["property_id"]),
                    "guestId": str(reservation["guest_id"]),
                    "roomId": str(room["room_id"]),
                    "roomNumber": room["room_number"],
                },
            )
        except Exception:
            # DB state is already committed; event publishing is best-effort.
            logger.exception("Failed to publish checkinout.checked_in event")

        return ok({
            "stayId": reservation_id,
            "roomId": str(room["room_id"]),
            "roomNumber": room["room_number"],
            "status": "CHECKED_IN",
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Unexpected error during check-in")
        return server_error()


def _get_specific_room(cur, room_id):
    cur.execute(
        "SELECT room_id, room_number, room_type_id, status, floor FROM rooms WHERE room_id = %s",
        [room_id],
    )
    return cur.fetchone()


def _find_available_room(cur, property_id, room_type_id):
    cur.execute(
        "SELECT room_id, room_number, room_type_id, status, floor FROM rooms "
        "WHERE property_id = %s AND room_type_id = %s AND status = 'AVAILABLE' "
        "ORDER BY floor DESC NULLS LAST, room_number ASC LIMIT 1",
        [property_id, room_type_id],
    )
    return cur.fetchone()

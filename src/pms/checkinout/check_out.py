"""
PMS Check-Out Handler.

POST /stays/{stayId}/checkout
Updates reservation status, sets room to DIRTY, advances Step Functions lifecycle.
Triggers billing and housekeeping via event.
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
        require_groups(event, "FrontDesk", "Manager", "Admin")
        staff_user_id = get_user_id(event)

        reservation_id = validate_uuid(
            event.get("pathParameters", {}).get("reservationId"), "reservationId"
        )
        body = parse_body(event) or {}
        express_checkout = body.get("expressCheckout", False)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT reservation_id, property_id, guest_id, room_id, "
                    "room_type_id, status, check_out_task_token "
                    "FROM reservations WHERE reservation_id = %s",
                    [reservation_id],
                )
                reservation = cur.fetchone()
                if not reservation:
                    return error(404, "NOT_FOUND", "Stay not found")

                verify_property_access(event, str(reservation["property_id"]))

                if reservation["status"] != "CHECKED_IN":
                    return error(
                        409, "INVALID_STATE",
                        f"Guest must be CHECKED_IN for checkout, current: {reservation['status']}"
                    )

                # Get room number for event
                cur.execute(
                    "SELECT room_number FROM rooms WHERE room_id = %s",
                    [reservation["room_id"]],
                )
                room = cur.fetchone()
                room_number = room["room_number"] if room else ""

                # Execute checkout
                cur.execute(
                    "UPDATE reservations SET status = 'CHECKED_OUT', "
                    "checked_out_at = now(), updated_at = now() WHERE reservation_id = %s",
                    [reservation_id],
                )
                cur.execute(
                    "UPDATE rooms SET status = 'DIRTY', updated_at = now() WHERE room_id = %s",
                    [reservation["room_id"]],
                )
                cur.execute(
                    "INSERT INTO checkinout_records "
                    "(reservation_id, property_id, guest_id, room_id, room_number, "
                    "record_type, performed_by) "
                    "VALUES (%s, %s, %s, %s, %s, 'CHECKOUT', %s)",
                    [
                        reservation_id, reservation["property_id"],
                        reservation["guest_id"], reservation["room_id"],
                        room_number, staff_user_id,
                    ],
                )
                conn.commit()

        # Advance Step Functions
        if reservation.get("check_out_task_token"):
            try:
                get_sfn_client().send_task_success(
                    taskToken=reservation["check_out_task_token"],
                    output=json.dumps({
                        "status": "CHECKED_OUT",
                        "expressCheckout": express_checkout,
                    }),
                )
            except Exception as e:
                logger.warning("Failed to advance SFN", error=str(e))

        # Publish event (triggers billing + housekeeping)
        try:
            publish_event(
                source="anycompany.pms",
                detail_type="checkinout.checked_out",
                detail={
                    "reservationId": reservation_id,
                    "propertyId": str(reservation["property_id"]),
                    "guestId": str(reservation["guest_id"]),
                    "roomId": str(reservation["room_id"]),
                    "roomNumber": room_number,
                    "expressCheckout": express_checkout,
                },
            )
        except Exception:
            # DB state is already committed; event publishing is best-effort.
            logger.exception("Failed to publish checkinout.checked_out event")

        return ok({"status": "CHECKED_OUT", "reservationId": reservation_id})

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Unexpected error during checkout")
        return server_error()

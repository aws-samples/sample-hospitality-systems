"""
PMS Housekeeping Event Consumer.

SQS consumer that creates housekeeping tasks from EventBridge events.
Handles: checkinout.checked_out, reservation.confirmed, reservation.cancelled
"""

import json
import os
import uuid
from utils.logger import get_logger
from utils.database import get_conn

logger = get_logger("pms-housekeeping")

SFN_CLIENT = None


def _pick(detail, *keys):
    """Return the first non-empty value from detail for any of the given keys."""
    for key in keys:
        value = detail.get(key)
        if value is not None and value != "":
            return value
    return None


def get_sfn_client():
    global SFN_CLIENT
    if SFN_CLIENT is None:
        import boto3
        SFN_CLIENT = boto3.client("stepfunctions")
    return SFN_CLIENT


@logger.inject_lambda_context
def handler(event, context):
    """Process SQS batch with partial failure reporting."""
    failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            detail_type = body.get("detail-type", "")
            detail = body.get("detail", {})

            if detail_type == "checkinout.checked_out":
                _create_checkout_task(detail)
            elif detail_type in ("reservation.confirmed", "reservation.created"):
                _create_pre_arrival_task(detail)
            elif detail_type == "reservation.cancelled":
                _cancel_pending_tasks(detail)
            else:
                logger.info("Ignoring unhandled event type", detail_type=detail_type)

        except Exception as e:
            logger.exception("Failed to process housekeeping event",
                           message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}


def _create_checkout_task(detail):
    """Create HIGH priority cleaning task on guest checkout."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    property_id = _pick(detail, "propertyId", "property_id")
    room_id = _pick(detail, "roomId", "room_id")
    room_number = _pick(detail, "roomNumber", "room_number") or ""

    if not all([reservation_id, property_id, room_id]):
        logger.error("Missing required fields in checkout event", detail=detail)
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Idempotency check
            cur.execute(
                "SELECT task_id FROM housekeeping_tasks "
                "WHERE reservation_id = %s AND task_type = 'CHECKOUT'",
                [reservation_id],
            )
            if cur.fetchone():
                logger.info("Checkout task already exists, skipping",
                           reservation_id=reservation_id)
                return

            task_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO housekeeping_tasks "
                "(task_id, property_id, room_id, room_number, task_type, priority, "
                "status, reservation_id) "
                "VALUES (%s, %s, %s, %s, 'CHECKOUT', 'HIGH', 'PENDING', %s)",
                [task_id, property_id, room_id, room_number, reservation_id],
            )
            conn.commit()

    # Start Step Functions workflow
    _start_housekeeping_dispatch(task_id, property_id, room_id, room_number)
    logger.info("Created checkout housekeeping task", task_id=task_id, room_number=room_number)


def _create_pre_arrival_task(detail):
    """Create NORMAL priority pre-arrival task on reservation confirmation."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    property_id = _pick(detail, "propertyId", "property_id")
    room_id = _pick(detail, "roomId", "room_id")  # May be None if room not yet assigned
    room_number = _pick(detail, "roomNumber", "room_number") or ""

    if not reservation_id or not property_id:
        logger.error("Missing required fields in confirmed event", detail=detail)
        return

    # Skip if no room assigned yet (task will be created at check-in time)
    if not room_id:
        logger.info("No room assigned yet, skipping pre-arrival task",
                   reservation_id=reservation_id)
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Idempotency check
            cur.execute(
                "SELECT task_id FROM housekeeping_tasks "
                "WHERE reservation_id = %s AND task_type = 'PRE_ARRIVAL'",
                [reservation_id],
            )
            if cur.fetchone():
                logger.info("Pre-arrival task already exists, skipping",
                           reservation_id=reservation_id)
                return

            task_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO housekeeping_tasks "
                "(task_id, property_id, room_id, room_number, task_type, priority, "
                "status, reservation_id) "
                "VALUES (%s, %s, %s, %s, 'PRE_ARRIVAL', 'NORMAL', 'PENDING', %s)",
                [task_id, property_id, room_id, room_number, reservation_id],
            )
            conn.commit()

    _start_housekeeping_dispatch(task_id, property_id, room_id, room_number)
    logger.info("Created pre-arrival housekeeping task", task_id=task_id)


def _cancel_pending_tasks(detail):
    """Cancel pending housekeeping tasks when reservation is cancelled."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    if not reservation_id:
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE housekeeping_tasks SET status = 'FAILED', "
                "notes = 'Cancelled: reservation cancelled', updated_at = now() "
                "WHERE reservation_id = %s AND status IN ('PENDING', 'ASSIGNED')",
                [reservation_id],
            )
            conn.commit()

    logger.info("Cancelled pending tasks for reservation", reservation_id=reservation_id)


def _start_housekeeping_dispatch(task_id, property_id, room_id, room_number):
    """Start the HousekeepingDispatch Step Functions workflow."""
    state_machine_arn = os.environ.get("HOUSEKEEPING_STATE_MACHINE_ARN", "")
    if not state_machine_arn:
        logger.warning("HOUSEKEEPING_STATE_MACHINE_ARN not configured")
        return

    try:
        get_sfn_client().start_execution(
            stateMachineArn=state_machine_arn,
            name=f"hk-{task_id}",
            input=json.dumps({
                "taskId": task_id,
                "propertyId": property_id,
                "roomId": room_id,
                "roomNumber": room_number,
            }),
        )
    except Exception as e:
        logger.exception("Failed to start housekeeping dispatch", task_id=task_id)

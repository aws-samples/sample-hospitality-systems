"""
PMS Billing Event Consumer.

SQS consumer that creates folios and triggers checkout billing.
Handles: reservation.confirmed, reservation.cancelled, checkinout.checked_out
"""

import json
import os
import uuid
from datetime import datetime, timedelta

from utils.database import get_conn
from utils.logger import get_logger

logger = get_logger("pms-billing")

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

            if detail_type in ("reservation.confirmed", "reservation.created"):
                _create_folio_with_charges(detail)
            elif detail_type == "reservation.cancelled":
                _void_folio(detail)
            elif detail_type in ("reservation.modified", "reservation.updated"):
                _update_folio_on_modification(detail)
            elif detail_type == "checkinout.checked_out":
                _start_checkout_billing(detail)
            else:
                logger.info("Ignoring unhandled event type", detail_type=detail_type)

        except Exception:
            logger.exception("Failed to process billing event",
                           message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}


def _create_folio_with_charges(detail):
    """Create folio and pre-calculate room rate charges."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    property_id = _pick(detail, "propertyId", "property_id")
    guest_id = _pick(detail, "guestId", "guest_id")
    check_in_date = _pick(detail, "checkInDate", "check_in_date")
    check_out_date = _pick(detail, "checkOutDate", "check_out_date")
    # CRS uses totalAfterTax, older events may use totalAmount — accept both
    total_amount = float(
        _pick(detail, "totalAfterTax", "total_after_tax", "totalAmount", "total_amount") or 0
    )

    if not all([reservation_id, property_id, guest_id, check_in_date, check_out_date]):
        logger.error("Missing required fields in confirmed event", detail=detail)
        return

    with get_conn() as conn, conn.cursor() as cur:
        # Idempotency check
        cur.execute(
            "SELECT folio_id FROM folios WHERE reservation_id = %s",
            [reservation_id],
        )
        if cur.fetchone():
            logger.info("Folio already exists, skipping", reservation_id=reservation_id)
            return

        # Calculate nights
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
        nights = (check_out - check_in).days
        if nights <= 0:
            nights = 1

        # Get nightly rate (from reservation total / nights as fallback)
        nightly_rate = round(float(total_amount) / nights, 2) if total_amount else 0

        # Create folio
        folio_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO folios "
            "(folio_id, reservation_id, property_id, guest_id, "
            "check_in_date, check_out_date, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'OPEN')",
            [folio_id, reservation_id, property_id, guest_id,
             check_in_date, check_out_date],
        )

        # Create room rate charges (one per night)
        for night in range(nights):
            charge_date = check_in + timedelta(days=night)
            charge_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO charges "
                "(charge_id, folio_id, charge_type, description, amount, charge_date) "
                "VALUES (%s, %s, 'ROOM_RATE', %s, %s, %s)",
                [
                    charge_id, folio_id,
                    f"Room charge - Night {night + 1}",
                    nightly_rate, str(charge_date),
                ],
            )

        conn.commit()

    logger.info("Created folio with charges",
               folio_id=folio_id, reservation_id=reservation_id, nights=nights)


def _void_folio(detail):
    """Void folio and all charges when reservation is cancelled."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    if not reservation_id:
        return

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT folio_id, status FROM folios WHERE reservation_id = %s",
            [reservation_id],
        )
        folio = cur.fetchone()
        if not folio:
            logger.info("No folio to void", reservation_id=reservation_id)
            return

        if folio["status"] != "OPEN":
            logger.info("Folio not in OPEN state, cannot void",
                       folio_id=str(folio["folio_id"]), status=folio["status"])
            return

        # Void folio
        cur.execute(
            "UPDATE folios SET status = 'VOID', updated_at = now() WHERE folio_id = %s",
            [folio["folio_id"]],
        )
        # Void all charges
        cur.execute(
            "UPDATE charges SET status = 'VOIDED', voided_at = now() "
            "WHERE folio_id = %s AND status = 'ACTIVE'",
            [folio["folio_id"]],
        )
        conn.commit()

    logger.info("Voided folio", folio_id=str(folio["folio_id"]), reservation_id=reservation_id)


def _start_checkout_billing(detail):
    """Start the CheckoutBilling Step Functions workflow."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    property_id = _pick(detail, "propertyId", "property_id")
    guest_id = _pick(detail, "guestId", "guest_id")

    state_machine_arn = os.environ.get("BILLING_STATE_MACHINE_ARN", "")
    if not state_machine_arn:
        logger.warning("BILLING_STATE_MACHINE_ARN not configured")
        return

    try:
        get_sfn_client().start_execution(
            stateMachineArn=state_machine_arn,
            name=f"bill-{reservation_id[:8]}-{uuid.uuid4().hex[:8]}",
            input=json.dumps({
                "reservationId": reservation_id,
                "propertyId": property_id,
                "guestId": guest_id,
            }),
        )
        logger.info("Started checkout billing workflow", reservation_id=reservation_id)
    except Exception:
        # Re-raised to the caller, which logs/handles it; log at warning here to
        # avoid double-counting this as a separate error.
        logger.warning("Failed to start billing workflow", reservation_id=reservation_id)
        raise


def _update_folio_on_modification(detail):
    """Update folio charges when reservation dates change."""
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    new_check_in = _pick(detail, "checkInDate", "check_in_date")
    new_check_out = _pick(detail, "checkOutDate", "check_out_date")
    total_amount = _pick(detail, "totalAmount", "total_amount", "totalAfterTax", "total_after_tax") or 0

    if not reservation_id:
        logger.error("Missing reservationId in modified event")
        return

    with get_conn() as conn, conn.cursor() as cur:
        # Find existing folio
        cur.execute(
            "SELECT folio_id, status, check_in_date, check_out_date "
            "FROM folios WHERE reservation_id = %s",
            [reservation_id],
        )
        folio = cur.fetchone()
        if not folio:
            logger.info("No folio to update for modification", reservation_id=reservation_id)
            return

        if folio["status"] != "OPEN":
            logger.info("Folio not OPEN, cannot modify", status=folio["status"])
            return

        folio_id = folio["folio_id"]

        # Check if dates actually changed
        old_check_in = str(folio["check_in_date"])
        old_check_out = str(folio["check_out_date"])

        if new_check_in == old_check_in and new_check_out == old_check_out:
            logger.info("Dates unchanged, skipping folio update")
            return

        # Void existing ROOM_RATE charges
        cur.execute(
            "UPDATE charges SET status = 'VOIDED', voided_at = now(), "
            "voided_by = 'system:reservation_modified' "
            "WHERE folio_id = %s AND charge_type = 'ROOM_RATE' AND status = 'ACTIVE'",
            [folio_id],
        )

        # Update folio dates
        cur.execute(
            "UPDATE folios SET check_in_date = %s, check_out_date = %s, updated_at = now() "
            "WHERE folio_id = %s",
            [new_check_in, new_check_out, folio_id],
        )

        # Recalculate room charges for new dates
        check_in = datetime.strptime(new_check_in, "%Y-%m-%d").date()
        check_out = datetime.strptime(new_check_out, "%Y-%m-%d").date()
        nights = (check_out - check_in).days
        if nights <= 0:
            nights = 1

        nightly_rate = round(float(total_amount) / nights, 2) if total_amount else 0

        for night in range(nights):
            charge_date = check_in + timedelta(days=night)
            charge_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO charges "
                "(charge_id, folio_id, charge_type, description, amount, charge_date) "
                "VALUES (%s, %s, 'ROOM_RATE', %s, %s, %s)",
                [charge_id, folio_id, f"Room charge - Night {night + 1}",
                 nightly_rate, str(charge_date)],
            )

        conn.commit()

    logger.info("Updated folio for reservation modification",
               reservation_id=reservation_id, old_dates=f"{old_check_in}/{old_check_out}",
               new_dates=f"{new_check_in}/{new_check_out}", nights=nights)

"""
PMS Loyalty Event Consumer.

SQS consumer triggered by billing.payment_processed event.
Earns points, increments total_stays, recalculates tier.
"""

import json

from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.loyalty import earn_points, recalculate_tier

logger = get_logger("pms-loyalty")


@logger.inject_lambda_context
def handler(event, context):
    """Process SQS batch with partial failure reporting."""
    failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            detail_type = body.get("detail-type", "")
            detail = body.get("detail", {})

            if detail_type == "billing.payment_processed":
                _earn_points_on_checkout(detail)
            else:
                logger.info("Ignoring unhandled event", detail_type=detail_type)

        except Exception:
            logger.exception("Failed to process loyalty event",
                           message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}


def _earn_points_on_checkout(detail):
    """Earn loyalty points after successful checkout payment."""
    reservation_id = detail.get("reservationId")
    guest_id = detail.get("guestId")
    folio_amount = float(detail.get("amount", 0))
    property_id = detail.get("propertyId")

    if not all([reservation_id, guest_id]):
        logger.error("Missing required fields in payment event", detail=detail)
        return

    with get_conn() as conn, conn.cursor() as cur:
        # Idempotency: check if points already earned for this reservation
        cur.execute(
            "SELECT transaction_id FROM loyalty_transactions "
            "WHERE reservation_id = %s AND transaction_type = 'EARN_STAY'",
            [reservation_id],
        )
        if cur.fetchone():
            logger.info("Points already earned for reservation, skipping",
                       reservation_id=reservation_id)
            return

        # Get reservation details for nights
        cur.execute(
            "SELECT check_in_date, check_out_date FROM reservations "
            "WHERE reservation_id = %s",
            [reservation_id],
        )
        reservation = cur.fetchone()
        if not reservation:
            logger.error("Reservation not found", reservation_id=reservation_id)
            return

        nights = (reservation["check_out_date"] - reservation["check_in_date"]).days
        if nights <= 0:
            nights = 1
        base_rate = folio_amount / nights if folio_amount > 0 else 100.0

        # Get current tier (before earning)
        cur.execute(
            "SELECT loyalty_tier, total_stays FROM guests WHERE guest_id = %s",
            [guest_id],
        )
        guest = cur.fetchone()
        if not guest:
            logger.error("Guest not found", guest_id=guest_id)
            return

        current_tier = guest["loyalty_tier"]

        # Earn points (atomic, uses SELECT FOR UPDATE internally)
        earn_result = earn_points(conn, guest_id, reservation_id, base_rate, nights, current_tier)

        # Increment total_stays
        cur.execute(
            "UPDATE guests SET total_stays = total_stays + 1, updated_at = now() "
            "WHERE guest_id = %s",
            [guest_id],
        )

        # Recalculate tier (may upgrade)
        new_tier = recalculate_tier(conn, guest_id)

        conn.commit()

    # Publish points earned event (best-effort)
    try:
        publish_event(
            source="anycompany.loyalty",
            detail_type="loyalty.points_earned",
            detail={
                "guestId": guest_id,
                "reservationId": reservation_id,
                "pointsEarned": earn_result["points_earned"],
                "newBalance": earn_result["new_balance"],
                "tier": current_tier,
                "propertyId": property_id,
            },
        )
    except Exception:
        logger.exception("Failed to publish loyalty.points_earned event")

    logger.info("Points earned",
               guest_id=guest_id, points=earn_result["points_earned"],
               new_balance=earn_result["new_balance"])

    # Publish tier change event if upgraded
    if new_tier:
        try:
            publish_event(
                source="anycompany.loyalty",
                detail_type="loyalty.tier_changed",
                detail={
                    "guestId": guest_id,
                    "previousTier": current_tier,
                    "newTier": new_tier,
                    "totalStays": guest["total_stays"] + 1,
                },
            )
        except Exception:
            logger.exception("Failed to publish loyalty.tier_changed event")
        logger.info("Tier upgraded", guest_id=guest_id,
                   from_tier=current_tier, to_tier=new_tier)

"""
PMS Redeem Loyalty Points.

POST /loyalty/{guestId}/redeem
Redeem points for rewards (e.g., free night = 10,000 points).
"""

import os
from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid, parse_body
from utils.loyalty import redeem_points as do_redeem_points
from utils.events import publish_event
from utils.tenant import require_groups, ForbiddenError

logger = get_logger("pms-loyalty")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        guest_id = validate_uuid(
            event.get("pathParameters", {}).get("guestId"), "guestId"
        )

        body = parse_body(event)
        if not body:
            return error(400, "VALIDATION_ERROR", "Request body is required")

        points = body.get("points")
        reservation_id = body.get("reservationId")

        if points is None or not isinstance(points, int) or points <= 0:
            return error(400, "VALIDATION_ERROR", "points must be a positive integer")

        if reservation_id:
            validate_uuid(reservation_id, "reservationId")

        with get_conn() as conn:
            try:
                result = do_redeem_points(
                    conn, guest_id, points, reservation_id,
                    description=f"Redeemed {points} points"
                )
                conn.commit()
            except ValueError as e:
                return error(400, "REDEMPTION_ERROR", str(e))

        # Publish event (best-effort; DB commit has already succeeded)
        try:
            publish_event(
                source="anycompany.loyalty",
                detail_type="loyalty.points_redeemed",
                detail={
                    "guestId": guest_id,
                    "pointsRedeemed": points,
                    "newBalance": result["new_balance"],
                    "reservationId": reservation_id,
                },
            )
        except Exception:
            logger.exception("Failed to publish loyalty.points_redeemed event")

        return ok({
            "transactionId": result["transaction_id"],
            "pointsRedeemed": result["points_redeemed"],
            "newBalance": result["new_balance"],
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except Exception as e:
        logger.exception("Error redeeming points")
        return server_error()

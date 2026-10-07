"""
PMS Adjust Loyalty Points.

POST /loyalty/{guestId}/adjust
Manual point adjustment (positive or negative) with required reason.
Admin and Manager only.
"""

from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.loyalty import adjust_points as do_adjust_points
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups
from utils.validation import parse_body, validate_uuid

logger = get_logger("pms-loyalty")


@logger.inject_lambda_context
def handler(event, context):
    try:
        # Only Manager and Admin can adjust points
        require_groups(event, "Manager", "Admin")

        guest_id = validate_uuid(
            event.get("pathParameters", {}).get("guestId"), "guestId"
        )

        body = parse_body(event)
        if not body:
            return error(400, "VALIDATION_ERROR", "Request body is required")

        points = body.get("points")
        reason = body.get("reason", "").strip()

        if points is None or not isinstance(points, int):
            return error(400, "VALIDATION_ERROR", "points must be an integer")
        if points == 0:
            return error(400, "VALIDATION_ERROR", "points cannot be zero")
        if not reason:
            return error(400, "VALIDATION_ERROR", "reason is required")
        if len(reason) > 500:
            return error(400, "VALIDATION_ERROR", "reason must be 500 characters or less")

        with get_conn() as conn:
            try:
                result = do_adjust_points(conn, guest_id, points, reason)
                conn.commit()
            except ValueError as e:
                return error(400, "ADJUSTMENT_ERROR", str(e))

        # Publish event (best-effort; DB commit has already succeeded)
        try:
            publish_event(
                source="anycompany.loyalty",
                detail_type="loyalty.points_adjusted",
                detail={
                    "guestId": guest_id,
                    "pointsAdjusted": points,
                    "newBalance": result["new_balance"],
                    "reason": reason,
                },
            )
        except Exception:
            logger.exception("Failed to publish loyalty.points_adjusted event")

        return ok({
            "transactionId": result["transaction_id"],
            "pointsAdjusted": result["points_adjusted"],
            "newBalance": result["new_balance"],
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except Exception:
        logger.exception("Error adjusting points")
        return server_error()

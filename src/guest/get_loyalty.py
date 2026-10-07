"""
Lambda handler for GET /guests/{guestId}/loyalty.

Returns basic loyalty info (tier, points balance, total stays) for the
authenticated guest's account page.
"""

from utils.auth import get_claims
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error

logger = get_logger("guest")


@logger.inject_lambda_context
def handler(event, context):
    try:
        # Guest can only view their own loyalty
        claims = get_claims(event)
        caller_sub = claims.get("sub", "")

        guest_id = event.get("pathParameters", {}).get("guestId")
        if not guest_id:
            return error(400, "VALIDATION_ERROR", "guestId is required")

        with get_conn() as conn, conn.cursor() as cur:
            # Load the guest, including cognito_sub so we can verify ownership.
            cur.execute(
                "SELECT guest_id, cognito_sub, loyalty_tier, points_balance, total_stays "
                "FROM guests WHERE guest_id = %s",
                [guest_id],
            )
            guest = cur.fetchone()

        if not guest:
            return error(404, "NOT_FOUND", "Guest not found")

        # Owner-only access: the caller may only read their own loyalty data.
        if guest["cognito_sub"] != caller_sub:
            return forbidden("You do not have permission to access this resource.")

        # Simple response for account page display
        return ok({
            "tier": guest["loyalty_tier"],
            "pointsBalance": guest["points_balance"],
            "totalStays": guest["total_stays"],
        })

    except Exception:
        logger.exception("Error getting guest loyalty")
        return server_error()

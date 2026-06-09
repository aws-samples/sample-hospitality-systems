"""
PMS Get Loyalty Profile.

GET /loyalty/{guestId}
Returns loyalty summary with tier, points, and progress to next tier.
"""

from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid
from utils.tenant import require_groups, ForbiddenError

logger = get_logger("pms-loyalty")

# Tier thresholds for progress calculation
TIER_THRESHOLDS = {
    "NONE": {"next": "SILVER", "stays_needed": 5},
    "SILVER": {"next": "GOLD", "stays_needed": 10},
    "GOLD": {"next": "DIAMOND", "stays_needed": 20},
    "DIAMOND": {"next": None, "stays_needed": None},
}


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        guest_id = validate_uuid(
            event.get("pathParameters", {}).get("guestId"), "guestId"
        )

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT guest_id, first_name, last_name, loyalty_tier, "
                    "points_balance, lifetime_points_earned, total_stays "
                    "FROM guests WHERE guest_id = %s",
                    [guest_id],
                )
                guest = cur.fetchone()
                if not guest:
                    return error(404, "NOT_FOUND", "Guest not found")

        # Calculate tier progress
        tier_info = TIER_THRESHOLDS.get(guest["loyalty_tier"], TIER_THRESHOLDS["NONE"])
        stays_to_next = None
        if tier_info["stays_needed"] is not None:
            stays_to_next = max(0, tier_info["stays_needed"] - guest["total_stays"])

        return ok({
            "guestId": str(guest["guest_id"]),
            "guestName": f"{guest['first_name']} {guest['last_name']}",
            "tier": guest["loyalty_tier"],
            "pointsBalance": guest["points_balance"],
            "lifetimePointsEarned": guest["lifetime_points_earned"],
            "totalStays": guest["total_stays"],
            "nextTier": tier_info["next"],
            "staysToNextTier": stays_to_next,
            "tierMultiplier": {"NONE": 1.0, "SILVER": 1.25, "GOLD": 1.5, "DIAMOND": 2.0}.get(
                guest["loyalty_tier"], 1.0
            ),
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error getting loyalty profile")
        return server_error()

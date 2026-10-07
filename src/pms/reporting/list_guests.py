"""
PMS List Guests.

GET /guests?q=&tier=&sort=&page=&limit=
Returns guest directory rows with loyalty + last/next stay context. Chain-wide
(no property scoping) — guests aren't owned by a property; property-pinned
staff still only see *stays* at their property via /stays.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups

logger = get_logger("pms-reporting")

VALID_TIERS = {"NONE", "SILVER", "GOLD", "DIAMOND"}
VALID_SORTS = {"name", "recent"}


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        params = event.get("queryStringParameters") or {}
        q = (params.get("q") or "").strip()
        tier = (params.get("tier") or "").strip().upper()
        sort = (params.get("sort") or "name").strip().lower()
        page = max(int(params.get("page", "1")), 1)
        limit = min(max(int(params.get("limit", "50")), 1), 200)
        offset = (page - 1) * limit

        if tier and tier not in VALID_TIERS:
            return error(400, "VALIDATION_ERROR", f"tier must be one of {sorted(VALID_TIERS)}")
        if sort not in VALID_SORTS:
            return error(400, "VALIDATION_ERROR", f"sort must be one of {sorted(VALID_SORTS)}")

        # q: optional full-text search.  When present, bind %q% once for the
        # NULL-test and then three times for the ILIKE matches.
        # tier: optional, NULL-guarded (bound twice).
        q_val = q if q else None
        q_like = f"%{q}%" if q else None
        tier_val = tier if tier else None

        filter_params = [
            q_val, q_like, q_like, q_like,
            tier_val, tier_val,
        ]

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total "
                "FROM guests g "
                "WHERE (%s::text IS NULL OR "
                "       (g.first_name ILIKE %s OR g.last_name ILIKE %s OR g.email ILIKE %s)) "
                "AND (%s::text IS NULL OR g.loyalty_tier = %s::text)",
                filter_params,
            )
            total = cur.fetchone()["total"]

            # Two fully-static fetch queries — pick by sort parameter.
            if sort == "recent":
                cur.execute(
                    "SELECT g.guest_id, g.first_name, g.last_name, g.email, g.phone, "
                    "g.loyalty_tier, g.points_balance, g.total_stays, "
                    "(SELECT MAX(r.check_in_date) FROM reservations r "
                    "   WHERE r.guest_id = g.guest_id "
                    "     AND r.status IN ('CHECKED_OUT', 'CHECKED_IN') "
                    ") AS last_stay_date, "
                    "(SELECT MIN(r.check_in_date) FROM reservations r "
                    "   WHERE r.guest_id = g.guest_id "
                    "     AND r.status IN ('CONFIRMED', 'CHECKED_IN') "
                    "     AND r.check_in_date >= CURRENT_DATE "
                    ") AS next_stay_date "
                    "FROM guests g "
                    "WHERE (%s::text IS NULL OR "
                    "       (g.first_name ILIKE %s OR g.last_name ILIKE %s OR g.email ILIKE %s)) "
                    "AND (%s::text IS NULL OR g.loyalty_tier = %s::text) "
                    "ORDER BY last_stay_date DESC NULLS LAST, g.last_name ASC "
                    "LIMIT %s OFFSET %s",
                    filter_params + [limit, offset],
                )
            else:
                cur.execute(
                    "SELECT g.guest_id, g.first_name, g.last_name, g.email, g.phone, "
                    "g.loyalty_tier, g.points_balance, g.total_stays, "
                    "(SELECT MAX(r.check_in_date) FROM reservations r "
                    "   WHERE r.guest_id = g.guest_id "
                    "     AND r.status IN ('CHECKED_OUT', 'CHECKED_IN') "
                    ") AS last_stay_date, "
                    "(SELECT MIN(r.check_in_date) FROM reservations r "
                    "   WHERE r.guest_id = g.guest_id "
                    "     AND r.status IN ('CONFIRMED', 'CHECKED_IN') "
                    "     AND r.check_in_date >= CURRENT_DATE "
                    ") AS next_stay_date "
                    "FROM guests g "
                    "WHERE (%s::text IS NULL OR "
                    "       (g.first_name ILIKE %s OR g.last_name ILIKE %s OR g.email ILIKE %s)) "
                    "AND (%s::text IS NULL OR g.loyalty_tier = %s::text) "
                    "ORDER BY g.last_name ASC, g.first_name ASC "
                    "LIMIT %s OFFSET %s",
                    filter_params + [limit, offset],
                )
            rows = cur.fetchall()

        guests = [
            {
                "guestId": str(r["guest_id"]),
                "firstName": r["first_name"],
                "lastName": r["last_name"],
                "guestName": f"{r['first_name']} {r['last_name']}",
                "email": r["email"],
                "phone": r["phone"],
                "loyaltyTier": r["loyalty_tier"],
                "pointsBalance": r["points_balance"],
                "totalStays": r["total_stays"],
                "lastStayDate": str(r["last_stay_date"]) if r["last_stay_date"] else None,
                "nextStayDate": str(r["next_stay_date"]) if r["next_stay_date"] else None,
            }
            for r in rows
        ]

        return ok({
            "guests": guests,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": (total + limit - 1) // limit if total else 0,
            },
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, "VALIDATION_ERROR", str(e))
    except Exception:
        logger.exception("Error listing guests")
        return server_error()

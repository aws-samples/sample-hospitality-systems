"""
PMS List Stays Handler.

GET /stays?propertyId=&status=&date=&page=&limit=
Lists check-in/out records and active stays for a property.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, resolve_property_scope
from utils.validation import validate_uuid

logger = get_logger("pms-checkinout")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        params = event.get("queryStringParameters") or {}
        status_filter = params.get("status")  # CHECKED_IN, CHECKED_OUT, CONFIRMED
        date_filter = params.get("date")  # YYYY-MM-DD
        page = int(params.get("page", "1"))
        limit = min(int(params.get("limit", "50")), 100)
        offset = (page - 1) * limit

        # Determine property scope. Fails closed when the caller is neither
        # property-pinned nor in a chain-level/regional group — an absent
        # custom:property_id claim is NOT read as chain-level access.
        requested_property_id = params.get("propertyId")
        if requested_property_id:
            validate_uuid(requested_property_id, "propertyId")
        # RegionalManager is not admitted by require_groups above, so
        # scope.region is always None here and needs no SQL predicate.
        property_id = resolve_property_scope(event, requested_property_id).property_id

        # Static queries; all filters use NULL-guard predicates so the SQL text
        # never changes.
        #
        # property_id: optional, NULL-guarded (bound twice).
        #
        # status_filter: optional, with a hardcoded default when absent.
        #   Logic: if status_filter IS NULL → apply default IN ('CONFIRMED','CHECKED_IN')
        #          if status_filter is given → match it exactly.
        #   Predicate (AND binds tighter than OR):
        #     (%s::text IS NULL AND r.status IN ('CONFIRMED','CHECKED_IN')
        #      OR r.status = %s::text)
        #   When status_filter=None:  TRUE AND default_in  OR  r.status=NULL
        #                          => r.status IN ('CONFIRMED','CHECKED_IN')
        #   When status_filter='X':   FALSE AND ...  OR  r.status='X'
        #                          => r.status='X'
        #
        # date_filter: optional, NULL-guarded (same value bound twice per side).
        filter_params = [
            property_id, property_id,
            status_filter, status_filter,
            date_filter, date_filter,
            date_filter, date_filter,
        ]

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as total "
                "FROM reservations r "
                "WHERE (%s::uuid IS NULL OR r.property_id = %s::uuid) "
                "AND (%s::text IS NULL AND r.status IN ('CONFIRMED','CHECKED_IN') "
                "     OR r.status = %s::text) "
                "AND (%s::date IS NULL OR r.check_in_date <= %s::date) "
                "AND (%s::date IS NULL OR r.check_out_date >= %s::date)",
                filter_params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                "SELECT r.reservation_id, r.property_id, r.guest_id, "
                "rt.name AS room_type, r.room_type_id, r.room_id, r.status, "
                "r.check_in_date, r.check_out_date, r.checked_in_at, r.checked_out_at, "
                "g.first_name, g.last_name, g.loyalty_tier, "
                "rm.room_number "
                "FROM reservations r "
                "LEFT JOIN guests g ON r.guest_id = g.guest_id "
                "LEFT JOIN rooms rm ON r.room_id = rm.room_id "
                "LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id "
                "WHERE (%s::uuid IS NULL OR r.property_id = %s::uuid) "
                "AND (%s::text IS NULL AND r.status IN ('CONFIRMED','CHECKED_IN') "
                "     OR r.status = %s::text) "
                "AND (%s::date IS NULL OR r.check_in_date <= %s::date) "
                "AND (%s::date IS NULL OR r.check_out_date >= %s::date) "
                "ORDER BY r.check_in_date ASC "
                "LIMIT %s OFFSET %s",
                filter_params + [limit, offset],
            )
            stays = cur.fetchall()

        return ok({
            "stays": [_format_stay(s) for s in stays],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": (total + limit - 1) // limit,
            },
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Unexpected error listing stays")
        return server_error()


def _format_stay(row):
    return {
        "reservationId": str(row["reservation_id"]),
        "propertyId": str(row["property_id"]),
        "guestId": str(row["guest_id"]),
        "guestName": f"{row['first_name']} {row['last_name']}",
        "loyaltyTier": row["loyalty_tier"],
        "roomType": row["room_type"],
        "roomId": str(row["room_id"]) if row["room_id"] else None,
        "roomNumber": row["room_number"],
        "status": row["status"],
        "checkInDate": str(row["check_in_date"]),
        "checkOutDate": str(row["check_out_date"]),
        "checkedInAt": row["checked_in_at"].isoformat() if row["checked_in_at"] else None,
        "checkedOutAt": row["checked_out_at"].isoformat() if row["checked_out_at"] else None,
    }

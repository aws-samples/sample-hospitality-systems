"""
PMS List Folios.

GET /billing/folios?propertyId=&status=&page=&limit=
Returns paginated list of folios for a property.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, resolve_property_scope
from utils.validation import validate_uuid

logger = get_logger("pms-billing")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        params = event.get("queryStringParameters") or {}
        status_filter = params.get("status")
        page = int(params.get("page", "1"))
        limit = min(int(params.get("limit", "50")), 100)
        offset = (page - 1) * limit

        # Fails closed when the caller is neither property-pinned nor in a
        # chain-level group — an absent custom:property_id claim is NOT read as
        # chain-level access. RegionalManager is not admitted by require_groups
        # above, so scope.region is always None here.
        requested_property_id = params.get("propertyId")
        if requested_property_id:
            validate_uuid(requested_property_id, "propertyId")
        property_id = resolve_property_scope(event, requested_property_id).property_id

        with get_conn() as conn, conn.cursor() as cur:
            # Static queries; optional filters use NULL-guard predicates
            # ((%s IS NULL OR col = %s)) so the SQL text never changes and an
            # absent filter is passed as NULL. Each optional value is bound
            # twice (once for the NULL test, once for the match).
            filter_params = [property_id, property_id, status_filter, status_filter]

            cur.execute(
                "SELECT COUNT(*) as total FROM folios f "
                "WHERE (%s::uuid IS NULL OR f.property_id = %s::uuid) "
                "AND (%s::text IS NULL OR f.status = %s::text)",
                filter_params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                "SELECT f.folio_id, f.reservation_id, f.property_id, f.guest_id, "
                "f.check_in_date, f.check_out_date, f.status, "
                "f.total_amount, f.paid_at, f.created_at, "
                "g.first_name, g.last_name "
                "FROM folios f "
                "LEFT JOIN guests g ON f.guest_id = g.guest_id "
                "WHERE (%s::uuid IS NULL OR f.property_id = %s::uuid) "
                "AND (%s::text IS NULL OR f.status = %s::text) "
                "ORDER BY f.created_at DESC "
                "LIMIT %s OFFSET %s",
                filter_params + [limit, offset],
            )
            folios = cur.fetchall()

        return ok({
            "folios": [
                {
                    "folioId": str(f["folio_id"]),
                    "reservationId": str(f["reservation_id"]),
                    "guestName": f"{f['first_name']} {f['last_name']}",
                    "checkInDate": str(f["check_in_date"]),
                    "checkOutDate": str(f["check_out_date"]),
                    "status": f["status"],
                    "totalAmount": float(f["total_amount"]) if f["total_amount"] else None,
                    "paidAt": f["paid_at"].isoformat() if f["paid_at"] else None,
                }
                for f in folios
            ],
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
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error listing folios")
        return server_error()

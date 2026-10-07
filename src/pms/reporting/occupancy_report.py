"""
PMS Occupancy Report.

GET /reporting/occupancy?startDate=&endDate=&region=
Returns occupancy rates across properties for a date range.
"""

from datetime import date

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, resolve_property_scope

logger = get_logger("pms-reporting")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin", "RegionalManager", "RevenueManager")

        params = event.get("queryStringParameters") or {}
        start_date = params.get("startDate", str(date.today()))
        end_date = params.get("endDate", str(date.today()))
        region_filter = params.get("region")

        # Scope by caller's access level. Precedence is handled by
        # resolve_property_scope: a property-scoped caller is pinned to their
        # property, a regional caller to their own region (and is denied
        # outright if that claim is missing rather than widened to the chain),
        # and only a chain-level caller may use the optional region query-param.
        # Bound as NULL-guard params on a static query (no SQL assembled from
        # strings).
        scope = resolve_property_scope(event)
        property_scope = scope.property_id
        region_scope = (
            None if property_scope else (scope.region or region_filter or None)
        )

        with get_conn() as conn, conn.cursor() as cur:
            # Get properties with room counts and current occupancy
            cur.execute(
                "SELECT p.property_id, p.name, p.city, p.region, "
                "COUNT(r.room_id) as total_rooms, "
                "COUNT(CASE WHEN r.status = 'OCCUPIED' THEN 1 END) as occupied_rooms "
                "FROM properties p "
                "LEFT JOIN rooms r ON p.property_id = r.property_id "
                "WHERE p.is_active = true "
                "AND (%s::uuid IS NULL OR p.property_id = %s::uuid) "
                "AND (%s::text IS NULL OR p.region = %s::text) "
                "GROUP BY p.property_id, p.name, p.city, p.region "
                "ORDER BY p.name",
                [property_scope, property_scope, region_scope, region_scope],
            )
            properties = cur.fetchall()

            property_ids = [p["property_id"] for p in properties]

            # Today's revenue per property (ROOM_RATE only, same source as
            # daily summary so headlines reconcile across views).
            revenue_by_prop: dict = {}
            checkin_by_prop: dict = {}
            checkout_by_prop: dict = {}
            if property_ids:
                cur.execute(
                    "SELECT f.property_id, COALESCE(SUM(c.amount), 0) AS revenue "
                    "FROM charges c JOIN folios f ON f.folio_id = c.folio_id "
                    "WHERE f.property_id = ANY(%s) "
                    "  AND c.charge_date = %s "
                    "  AND c.status = 'ACTIVE' "
                    "  AND c.charge_type = 'ROOM_RATE' "
                    "GROUP BY f.property_id",
                    [property_ids, end_date],
                )
                revenue_by_prop = {
                    str(r["property_id"]): float(r["revenue"]) for r in cur.fetchall()
                }

                cur.execute(
                    "SELECT property_id, record_type, COUNT(*) AS count "
                    "FROM checkinout_records "
                    "WHERE property_id = ANY(%s) "
                    "  AND DATE(recorded_at) = %s "
                    "GROUP BY property_id, record_type",
                    [property_ids, end_date],
                )
                for r in cur.fetchall():
                    pid = str(r["property_id"])
                    if r["record_type"] == "CHECKIN":
                        checkin_by_prop[pid] = int(r["count"])
                    elif r["record_type"] == "CHECKOUT":
                        checkout_by_prop[pid] = int(r["count"])

        results = []
        total_rooms_all = 0
        total_occupied_all = 0

        for prop in properties:
            total = prop["total_rooms"]
            occupied = prop["occupied_rooms"]
            pct = round((occupied / total * 100), 1) if total > 0 else 0
            total_rooms_all += total
            total_occupied_all += occupied

            pid = str(prop["property_id"])
            results.append({
                "propertyId": pid,
                "name": prop["name"],
                "city": prop["city"],
                "region": prop["region"],
                "totalRooms": total,
                "occupiedRooms": occupied,
                "occupancyPercent": pct,
                "revenueToday": revenue_by_prop.get(pid, 0.0),
                "checkInsToday": checkin_by_prop.get(pid, 0),
                "checkOutsToday": checkout_by_prop.get(pid, 0),
            })

        overall_pct = round((total_occupied_all / total_rooms_all * 100), 1) if total_rooms_all > 0 else 0

        return ok({
            "startDate": start_date,
            "endDate": end_date,
            "properties": results,
            "summary": {
                "totalProperties": len(results),
                "totalRooms": total_rooms_all,
                "totalOccupied": total_occupied_all,
                "overallOccupancy": overall_pct,
            },
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error generating occupancy report")
        return server_error()

"""
PMS Daily Summary Report.

GET /reporting/{propertyId}/daily?date=
Returns daily operational metrics for a property.
"""

from datetime import date, datetime
from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid
from utils.tenant import require_groups, verify_property_access, ForbiddenError

logger = get_logger("pms-reporting")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin", "RegionalManager", "RevenueManager")

        property_id = validate_uuid(
            event.get("pathParameters", {}).get("propertyId"), "propertyId"
        )
        verify_property_access(event, property_id)

        params = event.get("queryStringParameters") or {}
        report_date = params.get("date", str(date.today()))

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Reservations created today
                cur.execute(
                    "SELECT COUNT(*) as count FROM reservations "
                    "WHERE property_id = %s AND DATE(created_at) = %s",
                    [property_id, report_date],
                )
                reservations_created = cur.fetchone()["count"]

                # Check-ins today
                cur.execute(
                    "SELECT COUNT(*) as count FROM checkinout_records "
                    "WHERE property_id = %s AND DATE(recorded_at) = %s "
                    "AND record_type = 'CHECKIN'",
                    [property_id, report_date],
                )
                check_ins = cur.fetchone()["count"]

                # Check-outs today
                cur.execute(
                    "SELECT COUNT(*) as count FROM checkinout_records "
                    "WHERE property_id = %s AND DATE(recorded_at) = %s "
                    "AND record_type = 'CHECKOUT'",
                    [property_id, report_date],
                )
                check_outs = cur.fetchone()["count"]

                # Current occupancy
                cur.execute(
                    "SELECT COUNT(*) as total FROM rooms WHERE property_id = %s",
                    [property_id],
                )
                total_rooms = cur.fetchone()["total"]

                cur.execute(
                    "SELECT COUNT(*) as occupied FROM rooms "
                    "WHERE property_id = %s AND status = 'OCCUPIED'",
                    [property_id],
                )
                occupied = cur.fetchone()["occupied"]

                # Room revenue for the date — exclude tax and ad-hoc charges so
                # the headline "Revenue" reflects rooms sold that night, the
                # standard hotel convention.
                cur.execute(
                    "SELECT COALESCE(SUM(c.amount), 0) as revenue, "
                    "COUNT(DISTINCT c.folio_id) as rooms_sold "
                    "FROM charges c JOIN folios f ON c.folio_id = f.folio_id "
                    "WHERE f.property_id = %s AND c.charge_date = %s "
                    "AND c.status = 'ACTIVE' AND c.charge_type = 'ROOM_RATE'",
                    [property_id, report_date],
                )
                row = cur.fetchone()
                room_revenue = float(row["revenue"])
                rooms_sold = int(row["rooms_sold"])

                # Tax posted on the date (separate metric so it doesn't
                # contaminate room revenue but stays visible).
                cur.execute(
                    "SELECT COALESCE(SUM(c.amount), 0) as tax "
                    "FROM charges c JOIN folios f ON c.folio_id = f.folio_id "
                    "WHERE f.property_id = %s AND c.charge_date = %s "
                    "AND c.status = 'ACTIVE' AND c.charge_type = 'TAX'",
                    [property_id, report_date],
                )
                tax_posted = float(cur.fetchone()["tax"])

                # Payments collected today (cash-flow view, by payment date).
                cur.execute(
                    "SELECT COALESCE(SUM(p.amount), 0) as payments, "
                    "COUNT(*) as payment_count "
                    "FROM payments p JOIN folios f ON p.folio_id = f.folio_id "
                    "WHERE f.property_id = %s AND DATE(p.created_at) = %s "
                    "AND p.status = 'APPROVED'",
                    [property_id, report_date],
                )
                pay_row = cur.fetchone()
                payments_collected = float(pay_row["payments"])
                payments_count = int(pay_row["payment_count"])

                # Housekeeping tasks completed today
                cur.execute(
                    "SELECT COUNT(*) as count FROM housekeeping_tasks "
                    "WHERE property_id = %s AND DATE(completed_at) = %s",
                    [property_id, report_date],
                )
                tasks_completed = cur.fetchone()["count"]

        occupancy_pct = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
        # True ADR: room revenue divided by number of rooms sold that night.
        # Falls back to 0 when no rooms were sold (avoids div-by-zero).
        adr = round(room_revenue / rooms_sold, 2) if rooms_sold > 0 else 0

        return ok({
            "propertyId": property_id,
            "date": report_date,
            "reservationsCreated": reservations_created,
            "checkIns": check_ins,
            "checkOuts": check_outs,
            "occupancy": {
                "totalRooms": total_rooms,
                "occupied": occupied,
                "percent": occupancy_pct,
            },
            "revenue": room_revenue,
            "roomsSold": rooms_sold,
            "taxPosted": tax_posted,
            "paymentsCollected": payments_collected,
            "paymentsCount": payments_count,
            "adr": adr,
            "housekeepingTasksCompleted": tasks_completed,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error generating daily summary")
        return server_error()

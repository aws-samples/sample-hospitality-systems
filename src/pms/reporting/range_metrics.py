"""
PMS Range Metrics Report.

GET /reporting/range?propertyId=<uuid|_all>&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

Returns period totals + a per-day breakdown across the requested date range,
scoped to either a single property or the chain-wide (or region-wide) aggregate
for callers with chain-level / regional groups.

Powers the overview on the PMS Reports page (period KPIs,
daily revenue / room-nights bars, occupancy % line, portfolio summary).

Design notes:
- Revenue: sum of `charges.amount WHERE charge_type='ROOM_RATE' AND status='ACTIVE'`,
  grouped by `charge_date`. Same source the daily summary uses, so headline numbers
  reconcile across the two views.
- Room nights: count of distinct active ROOM_RATE charge rows per day. One charge
  per occupied room-night under the current schema, matching ADR semantics.
- Occupancy %: room-nights sold / total active rooms in scope today. Total rooms is
  the current count from the `rooms` table — a reasonable approximation for ranges
  up to ~3 months when room inventory is stable.
- Reservations created / cancelled: counted by DATE(created_at) and DATE(cancelled_at).
- Check-ins / check-outs: counted from `checkinout_records` by DATE(recorded_at).
- Range is capped at 92 days to keep the SQL fast and the response small.
"""

from datetime import date, datetime, timedelta

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import (
    ForbiddenError,
    require_groups,
    resolve_property_scope,
)
from utils.validation import validate_uuid

logger = get_logger("pms-reporting")

MAX_RANGE_DAYS = 92
CHAIN_WIDE_SENTINEL = "_all"


def _parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD") from None


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin", "RegionalManager", "RevenueManager")

        params = event.get("queryStringParameters") or {}
        requested_property_id = (params.get("propertyId") or "").strip() or None
        end_date = _parse_date(
            params.get("endDate", str(date.today())), "endDate"
        )
        start_date = _parse_date(
            params.get("startDate", str(end_date - timedelta(days=29))),
            "startDate",
        )

        if start_date > end_date:
            raise ValueError("startDate must be on or before endDate")
        span_days = (end_date - start_date).days + 1
        if span_days > MAX_RANGE_DAYS:
            raise ValueError(f"Date range too large (max {MAX_RANGE_DAYS} days)")

        # Resolve the effective property scope. Property-pinned callers cannot
        # widen to the chain aggregate; regional callers see only their region.
        # resolve_property_scope() derives the caller's level from the group
        # claim and denies outright when there is no property claim and no
        # qualifying group (and when a regional caller has no region), so an
        # absent claim can never widen the scope.
        narrowed = (
            None if requested_property_id == CHAIN_WIDE_SENTINEL
            else requested_property_id
        )
        if narrowed:
            validate_uuid(narrowed, "propertyId")
        scope = resolve_property_scope(event, narrowed)

        with get_conn() as conn, conn.cursor() as cur:
            # Resolve which property_ids are actually in scope. We always
            # materialize the list so SQL params stay simple, even for
            # chain-wide. Both scope dimensions are ANDed, so a regional
            # caller narrowing to a propertyId still cannot reach outside
            # their own region.
            cur.execute(
                "SELECT property_id FROM properties "
                "WHERE is_active = TRUE "
                "AND (%s::uuid IS NULL OR property_id = %s::uuid) "
                "AND (%s::text IS NULL OR region = %s::text)",
                [
                    scope.property_id, scope.property_id,
                    scope.region, scope.region,
                ],
            )
            in_scope = [str(r["property_id"]) for r in cur.fetchall()]

            if not in_scope:
                return ok({
                    "propertyId": requested_property_id or CHAIN_WIDE_SENTINEL,
                    "startDate": str(start_date),
                    "endDate": str(end_date),
                    "totals": _empty_totals(),
                    "dailyBreakdown": _zero_breakdown(start_date, end_date),
                })

            # Pre-build the contiguous date series so days with no activity
            # show up as zeroes.
            date_series = [
                start_date + timedelta(days=i) for i in range(span_days)
            ]
            breakdown = {
                d: {
                    "date": str(d),
                    "revenue": 0.0,
                    "roomNightsSold": 0,
                    "checkIns": 0,
                    "checkOuts": 0,
                    "reservationsCreated": 0,
                    "reservationsCancelled": 0,
                    "occupancyPercent": 0.0,
                }
                for d in date_series
            }

            # Total active rooms in scope (for occupancy %). Snapshot is fine
            # for ranges up to ~3 months.
            cur.execute(
                "SELECT COUNT(*) AS total FROM rooms "
                "WHERE property_id = ANY(%s)",
                [in_scope],
            )
            total_rooms = int(cur.fetchone()["total"])

            # Revenue + room nights — grouped by charge_date.
            cur.execute(
                "SELECT c.charge_date AS day, "
                "  COALESCE(SUM(c.amount), 0) AS revenue, "
                "  COUNT(*) AS room_nights "
                "FROM charges c "
                "JOIN folios f ON f.folio_id = c.folio_id "
                "WHERE f.property_id = ANY(%s) "
                "  AND c.charge_date BETWEEN %s AND %s "
                "  AND c.status = 'ACTIVE' "
                "  AND c.charge_type = 'ROOM_RATE' "
                "GROUP BY c.charge_date",
                [in_scope, start_date, end_date],
            )
            for row in cur.fetchall():
                day = row["day"]
                if day in breakdown:
                    breakdown[day]["revenue"] = float(row["revenue"])
                    breakdown[day]["roomNightsSold"] = int(row["room_nights"])

            # Reservations created.
            cur.execute(
                "SELECT DATE(created_at) AS day, COUNT(*) AS count "
                "FROM reservations "
                "WHERE property_id = ANY(%s) "
                "  AND DATE(created_at) BETWEEN %s AND %s "
                "GROUP BY DATE(created_at)",
                [in_scope, start_date, end_date],
            )
            for row in cur.fetchall():
                day = row["day"]
                if day in breakdown:
                    breakdown[day]["reservationsCreated"] = int(row["count"])

            # Reservations cancelled (only those that landed in CANCELLED
            # state and have a cancelled_at timestamp).
            cur.execute(
                "SELECT DATE(cancelled_at) AS day, COUNT(*) AS count "
                "FROM reservations "
                "WHERE property_id = ANY(%s) "
                "  AND status = 'CANCELLED' "
                "  AND cancelled_at IS NOT NULL "
                "  AND DATE(cancelled_at) BETWEEN %s AND %s "
                "GROUP BY DATE(cancelled_at)",
                [in_scope, start_date, end_date],
            )
            for row in cur.fetchall():
                day = row["day"]
                if day in breakdown:
                    breakdown[day]["reservationsCancelled"] = int(row["count"])

            # Check-ins / check-outs.
            cur.execute(
                "SELECT DATE(recorded_at) AS day, record_type, COUNT(*) AS count "
                "FROM checkinout_records "
                "WHERE property_id = ANY(%s) "
                "  AND DATE(recorded_at) BETWEEN %s AND %s "
                "GROUP BY DATE(recorded_at), record_type",
                [in_scope, start_date, end_date],
            )
            for row in cur.fetchall():
                day = row["day"]
                if day not in breakdown:
                    continue
                if row["record_type"] == "CHECKIN":
                    breakdown[day]["checkIns"] = int(row["count"])
                elif row["record_type"] == "CHECKOUT":
                    breakdown[day]["checkOuts"] = int(row["count"])

        # Compute occupancy % per day and roll up totals.
        totals = _empty_totals()
        daily_breakdown = []
        for d in date_series:
            row = breakdown[d]
            if total_rooms > 0:
                row["occupancyPercent"] = round(
                    row["roomNightsSold"] / total_rooms * 100, 1
                )
            totals["revenue"] += row["revenue"]
            totals["roomNightsSold"] += row["roomNightsSold"]
            totals["reservationsCreated"] += row["reservationsCreated"]
            totals["reservationsCancelled"] += row["reservationsCancelled"]
            totals["checkIns"] += row["checkIns"]
            totals["checkOuts"] += row["checkOuts"]
            daily_breakdown.append(row)

        # Average occupancy % across the range (simple mean of daily %).
        if total_rooms > 0 and span_days > 0:
            totals["averageOccupancyPercent"] = round(
                sum(d["occupancyPercent"] for d in daily_breakdown) / span_days, 1
            )
        else:
            totals["averageOccupancyPercent"] = 0.0

        totals["revenue"] = round(totals["revenue"], 2)
        totals["totalRooms"] = total_rooms
        totals["propertyCount"] = len(in_scope)

        return ok({
            "propertyId": requested_property_id or CHAIN_WIDE_SENTINEL,
            "startDate": str(start_date),
            "endDate": str(end_date),
            "totals": totals,
            "dailyBreakdown": daily_breakdown,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, "VALIDATION_ERROR", str(e))
    except Exception:
        logger.exception("Error generating range metrics")
        return server_error()


def _empty_totals() -> dict:
    return {
        "revenue": 0.0,
        "roomNightsSold": 0,
        "reservationsCreated": 0,
        "reservationsCancelled": 0,
        "checkIns": 0,
        "checkOuts": 0,
        "averageOccupancyPercent": 0.0,
        "totalRooms": 0,
        "propertyCount": 0,
    }


def _zero_breakdown(start: date, end: date) -> list[dict]:
    return [
        {
            "date": str(start + timedelta(days=i)),
            "revenue": 0.0,
            "roomNightsSold": 0,
            "checkIns": 0,
            "checkOuts": 0,
            "reservationsCreated": 0,
            "reservationsCancelled": 0,
            "occupancyPercent": 0.0,
        }
        for i in range((end - start).days + 1)
    ]

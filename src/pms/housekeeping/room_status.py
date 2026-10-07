"""
PMS Room Status Summary.

GET /housekeeping/rooms/summary
Returns room status counts for the property (visual board data).

Scoping:
- Property-level users: automatically scoped to their assigned property_id.
- Chain-level users (Admin/Manager/RevenueManager): may pass `propertyId` as a
  query param to scope to a single property, or omit it to get an aggregate
  across all active properties.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, resolve_property_scope
from utils.validation import validate_uuid

logger = get_logger("pms-housekeeping")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Housekeeping", "FrontDesk", "Manager", "Admin", "RevenueManager")

        # Property-level users always get their own property scope; chain-level
        # users may optionally narrow to a specific property. Fails closed when
        # the caller is neither — an absent custom:property_id claim is NOT read
        # as chain-level access. RegionalManager is not admitted by
        # require_groups above, so scope.region is always None here.
        params = event.get("queryStringParameters") or {}
        requested_property_id = params.get("propertyId")
        if requested_property_id:
            validate_uuid(requested_property_id, "propertyId")
        property_id = resolve_property_scope(event, requested_property_id).property_id

        with get_conn() as conn, conn.cursor() as cur:
            if property_id:
                cur.execute(
                    "SELECT status, COUNT(*) AS count "
                    "FROM rooms WHERE property_id = %s "
                    "GROUP BY status",
                    [property_id],
                )
            else:
                # Aggregate across all active properties for chain-level users.
                cur.execute(
                    "SELECT r.status, COUNT(*) AS count "
                    "FROM rooms r "
                    "JOIN properties p ON p.property_id = r.property_id "
                    "WHERE p.is_active = TRUE "
                    "GROUP BY r.status"
                )
            status_counts = {row["status"]: row["count"] for row in cur.fetchall()}

            total = sum(status_counts.values())

            # Rooms by floor (for visual board). Limited to a single property
            # because the floor plan view only makes sense per-property.
            rooms = []
            if property_id:
                cur.execute(
                    "SELECT r.room_id, r.room_number, r.floor, rt.name AS room_type, r.status "
                    "FROM rooms r "
                    "LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id "
                    "WHERE r.property_id = %s "
                    "ORDER BY r.floor DESC, r.room_number ASC",
                    [property_id],
                )
                rooms = cur.fetchall()

        occupied = status_counts.get("OCCUPIED", 0)
        occupancy_pct = round((occupied / total * 100), 1) if total > 0 else 0

        return ok({
            "propertyId": property_id,  # None for chain-level aggregate
            "scope": "property" if property_id else "chain",
            "totalRooms": total,
            "occupancyPercent": occupancy_pct,
            "available": status_counts.get("AVAILABLE", 0),
            "occupied": occupied,
            "dirty": status_counts.get("DIRTY", 0),
            "cleaning": status_counts.get("CLEANING", 0),
            "inspecting": status_counts.get("INSPECTING", 0),
            "outOfOrder": status_counts.get("OUT_OF_ORDER", 0),
            "rooms": [
                {
                    "roomId": str(r["room_id"]),
                    "roomNumber": r["room_number"],
                    "floor": r["floor"],
                    "roomType": r["room_type"],
                    "status": r["status"],
                }
                for r in rooms
            ],
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error getting room status summary")
        return server_error()

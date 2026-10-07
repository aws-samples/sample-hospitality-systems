"""
PMS List Housekeeping Tasks.

GET /housekeeping/tasks?status=&priority=&floor=&assignedTo=&page=&limit=
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
        require_groups(event, "Housekeeping", "Manager", "Admin")

        params = event.get("queryStringParameters") or {}
        status_filter = params.get("status")
        priority_filter = params.get("priority")
        assigned_to = params.get("assignedTo")
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

        # Static queries; all filters are optional (NULL-guarded, each bound twice).
        filter_params = [
            property_id, property_id,
            status_filter, status_filter,
            priority_filter, priority_filter,
            assigned_to, assigned_to,
        ]

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as total "
                "FROM housekeeping_tasks t "
                "WHERE (%s::uuid IS NULL OR t.property_id = %s::uuid) "
                "AND (%s::text IS NULL OR t.status = %s::text) "
                "AND (%s::text IS NULL OR t.priority = %s::text) "
                "AND (%s::text IS NULL OR t.assigned_to = %s::text)",
                filter_params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                "SELECT t.task_id, t.property_id, t.room_id, t.room_number, "
                "t.task_type, t.priority, t.status, t.assigned_to, t.notes, "
                "t.reservation_id, t.completed_at, t.inspected_at, "
                "t.created_at, t.updated_at "
                "FROM housekeeping_tasks t "
                "WHERE (%s::uuid IS NULL OR t.property_id = %s::uuid) "
                "AND (%s::text IS NULL OR t.status = %s::text) "
                "AND (%s::text IS NULL OR t.priority = %s::text) "
                "AND (%s::text IS NULL OR t.assigned_to = %s::text) "
                "ORDER BY "
                "CASE t.priority WHEN 'HIGH' THEN 1 WHEN 'NORMAL' THEN 2 ELSE 3 END, "
                "t.created_at ASC "
                "LIMIT %s OFFSET %s",
                filter_params + [limit, offset],
            )
            tasks = cur.fetchall()

        return ok({
            "tasks": [_format_task(t) for t in tasks],
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
        logger.exception("Error listing tasks")
        return server_error()


def _format_task(row):
    return {
        "taskId": str(row["task_id"]),
        "propertyId": str(row["property_id"]),
        "roomId": str(row["room_id"]),
        "roomNumber": row["room_number"],
        "taskType": row["task_type"],
        "priority": row["priority"],
        "status": row["status"],
        "assignedTo": row["assigned_to"],
        "notes": row["notes"],
        "reservationId": str(row["reservation_id"]) if row["reservation_id"] else None,
        "completedAt": row["completed_at"].isoformat() if row["completed_at"] else None,
        "inspectedAt": row["inspected_at"].isoformat() if row["inspected_at"] else None,
        "createdAt": row["created_at"].isoformat(),
    }

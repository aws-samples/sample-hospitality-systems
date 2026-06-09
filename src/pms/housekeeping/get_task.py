"""
PMS Get Housekeeping Task.

GET /housekeeping/tasks/{taskId}
Returns a single task with full details.
"""

from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid
from utils.tenant import require_groups, verify_property_access, ForbiddenError

logger = get_logger("pms-housekeeping")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Housekeeping", "Manager", "Admin")

        task_id = validate_uuid(
            event.get("pathParameters", {}).get("taskId"), "taskId"
        )

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT t.task_id, t.property_id, t.room_id, t.room_number, "
                    "t.task_type, t.priority, t.status, t.assigned_to, t.notes, "
                    "t.reservation_id, t.completed_at, t.inspected_at, "
                    "t.created_at, t.updated_at, "
                    "rt.name AS room_type, r.floor "
                    "FROM housekeeping_tasks t "
                    "LEFT JOIN rooms r ON t.room_id = r.room_id "
                    "LEFT JOIN room_types rt ON r.room_type_id = rt.room_type_id "
                    "WHERE t.task_id = %s",
                    [task_id],
                )
                task = cur.fetchone()

        if not task:
            return error(404, "NOT_FOUND", "Task not found")

        verify_property_access(event, str(task["property_id"]))

        return ok({
            "taskId": str(task["task_id"]),
            "propertyId": str(task["property_id"]),
            "roomId": str(task["room_id"]),
            "roomNumber": task["room_number"],
            "roomType": task["room_type"],
            "floor": task["floor"],
            "taskType": task["task_type"],
            "priority": task["priority"],
            "status": task["status"],
            "assignedTo": task["assigned_to"],
            "notes": task["notes"],
            "reservationId": str(task["reservation_id"]) if task["reservation_id"] else None,
            "completedAt": task["completed_at"].isoformat() if task["completed_at"] else None,
            "inspectedAt": task["inspected_at"].isoformat() if task["inspected_at"] else None,
            "createdAt": task["created_at"].isoformat(),
            "updatedAt": task["updated_at"].isoformat(),
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error getting task")
        return server_error()

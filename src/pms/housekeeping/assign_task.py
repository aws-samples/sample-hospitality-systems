"""
PMS Assign Housekeeping Task.

PUT /housekeeping/tasks/{taskId}/assign
Assign a task to a specific housekeeper.
"""

from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid, parse_body
from utils.tenant import require_groups, verify_property_access, ForbiddenError

logger = get_logger("pms-housekeeping")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Housekeeping", "Manager", "Admin")

        task_id = validate_uuid(
            event.get("pathParameters", {}).get("taskId"), "taskId"
        )

        body = parse_body(event)
        if not body or not body.get("assignedTo"):
            return error(400, "VALIDATION_ERROR", "assignedTo is required")

        assigned_to = body["assignedTo"].strip()
        if len(assigned_to) > 100:
            return error(400, "VALIDATION_ERROR", "assignedTo must be 100 characters or less")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_id, property_id, status, assigned_to "
                    "FROM housekeeping_tasks WHERE task_id = %s",
                    [task_id],
                )
                task = cur.fetchone()
                if not task:
                    return error(404, "NOT_FOUND", "Task not found")

                verify_property_access(event, str(task["property_id"]))

                if task["status"] not in ("PENDING", "ASSIGNED"):
                    return error(
                        409, "INVALID_STATE",
                        f"Can only assign PENDING or ASSIGNED tasks, current: {task['status']}"
                    )

                cur.execute(
                    "UPDATE housekeeping_tasks SET assigned_to = %s, status = 'ASSIGNED', "
                    "updated_at = now() WHERE task_id = %s",
                    [assigned_to, task_id],
                )
                conn.commit()

        return ok({
            "taskId": task_id,
            "assignedTo": assigned_to,
            "status": "ASSIGNED",
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error assigning task")
        return server_error()

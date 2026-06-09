"""
PMS Complete Housekeeping Task.

POST /housekeeping/tasks/{taskId}/complete
Marks cleaning as complete, advances Step Functions workflow.
"""

import json
import os
from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid, parse_body
from utils.tenant import require_groups, verify_property_access, ForbiddenError

logger = get_logger("pms-housekeeping")

SFN_CLIENT = None


def get_sfn_client():
    global SFN_CLIENT
    if SFN_CLIENT is None:
        import boto3
        SFN_CLIENT = boto3.client("stepfunctions")
    return SFN_CLIENT


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Housekeeping", "Manager", "Admin")

        task_id = validate_uuid(
            event.get("pathParameters", {}).get("taskId"), "taskId"
        )
        body = parse_body(event) or {}
        notes = body.get("notes", "")
        if notes and len(notes) > 2000:
            return error(400, "VALIDATION_ERROR", "Notes must be 2000 characters or less")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_id, property_id, room_id, status, cleaning_task_token "
                    "FROM housekeeping_tasks WHERE task_id = %s",
                    [task_id],
                )
                task = cur.fetchone()
                if not task:
                    return error(404, "NOT_FOUND", "Task not found")

                verify_property_access(event, str(task["property_id"]))

                # Validate state
                if task["status"] not in ("ASSIGNED", "CLEANING"):
                    return error(
                        409, "INVALID_STATE",
                        f"Task must be ASSIGNED or CLEANING to complete, current: {task['status']}"
                    )

                # Update task
                cur.execute(
                    "UPDATE housekeeping_tasks SET status = 'COMPLETED', "
                    "completed_at = now(), notes = COALESCE(%s, notes), updated_at = now() "
                    "WHERE task_id = %s",
                    [notes or None, task_id],
                )
                conn.commit()

        # Advance Step Functions
        if task.get("cleaning_task_token"):
            try:
                get_sfn_client().send_task_success(
                    taskToken=task["cleaning_task_token"],
                    output=json.dumps({"taskId": task_id, "status": "COMPLETED"}),
                )
            except Exception as e:
                logger.warning("Failed to advance SFN cleaning", error=str(e))

        return ok({"taskId": task_id, "status": "COMPLETED"})

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error completing task")
        return server_error()

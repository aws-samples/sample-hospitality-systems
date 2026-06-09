"""
PMS Inspect Housekeeping Task.

POST /housekeeping/tasks/{taskId}/inspect
Pass or fail room inspection after cleaning.
"""

import json
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

        body = parse_body(event)
        if not body or "passed" not in body:
            return error(400, "VALIDATION_ERROR", "passed (boolean) is required")

        passed = bool(body["passed"])
        notes = body.get("notes", "")
        if notes and len(notes) > 2000:
            return error(400, "VALIDATION_ERROR", "notes must be 2000 characters or less")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_id, property_id, room_id, status, inspection_task_token "
                    "FROM housekeeping_tasks WHERE task_id = %s",
                    [task_id],
                )
                task = cur.fetchone()
                if not task:
                    return error(404, "NOT_FOUND", "Task not found")

                verify_property_access(event, str(task["property_id"]))

                if task["status"] != "INSPECTING":
                    return error(
                        409, "INVALID_STATE",
                        f"Task must be in INSPECTING status, current: {task['status']}"
                    )

                if passed:
                    cur.execute(
                        "UPDATE housekeeping_tasks SET status = 'INSPECTED', "
                        "inspected_at = now(), notes = COALESCE(%s, notes), updated_at = now() "
                        "WHERE task_id = %s",
                        [notes or None, task_id],
                    )
                else:
                    # Record the failure reason in notes, but leave status alone:
                    # the SFN's InspectionDecision will route back to
                    # UpdateRoomToCleaning, which transitions the task to
                    # CLEANING via store_cleaning_token. Setting FAILED here
                    # would orphan the task because the loop-back overwrites it.
                    cur.execute(
                        "UPDATE housekeeping_tasks SET notes = %s, updated_at = now() "
                        "WHERE task_id = %s",
                        [f"Inspection failed: {notes}" if notes else "Inspection failed", task_id],
                    )

                conn.commit()

        # Advance Step Functions. Both pass and fail are reported via
        # send_task_success — the InspectionDecision Choice state in the ASL
        # branches on `passed`, looping back to cleaning when false. Calling
        # send_task_failure would terminate the execution and strand the room
        # in INSPECTING.
        if task.get("inspection_task_token"):
            try:
                get_sfn_client().send_task_success(
                    taskToken=task["inspection_task_token"],
                    output=json.dumps({"taskId": task_id, "passed": passed}),
                )
            except Exception as e:
                logger.warning("Failed to advance SFN inspection", error=str(e))

        result_status = "INSPECTED" if passed else "CLEANING"
        return ok({
            "taskId": task_id,
            "passed": passed,
            "status": result_status,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error inspecting task")
        return server_error()

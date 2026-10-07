"""
PMS Housekeeping Step Functions Actions.

Lambda invoked by Step Functions for state transitions.
Handles: store tokens, update room status (with OCCUPIED guard), record completions.
"""

from utils.database import get_conn
from utils.logger import get_logger

logger = get_logger("pms-housekeeping-sfn")


@logger.inject_lambda_context
def handler(event, context):
    """Route to appropriate action based on event input."""
    action = event.get("action")
    task_id = event.get("taskId")

    logger.info("SFN action", action=action, task_id=task_id)

    actions = {
        "store_cleaning_token": _store_cleaning_token,
        "store_inspection_token": _store_inspection_token,
        "update_room_to_cleaning": _update_room_to_cleaning,
        "update_room_to_inspecting": _update_room_to_inspecting,
        "update_room_to_available": _update_room_to_available,
        "record_cleaning_complete": _record_cleaning_complete,
        "record_inspection_complete": _record_inspection_complete,
    }

    if action not in actions:
        raise ValueError(f"Unknown action: {action}")

    return actions[action](event)


def _store_cleaning_token(event):
    """Store the cleaning task token for later SendTaskSuccess."""
    task_id = event["taskId"]
    task_token = event["taskToken"]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE housekeeping_tasks SET cleaning_task_token = %s, "
            "status = 'CLEANING', updated_at = now() WHERE task_id = %s",
            [task_token, task_id],
        )
        conn.commit()

    return {"taskId": task_id, "status": "CLEANING"}


def _store_inspection_token(event):
    """Store the inspection task token for later SendTaskSuccess."""
    task_id = event["taskId"]
    task_token = event["taskToken"]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE housekeeping_tasks SET inspection_task_token = %s, "
            "status = 'INSPECTING', updated_at = now() WHERE task_id = %s",
            [task_token, task_id],
        )
        conn.commit()

    return {"taskId": task_id, "status": "INSPECTING"}


def _update_room_to_cleaning(event):
    """Update room status to CLEANING (with OCCUPIED guard)."""
    room_id = event["roomId"]
    return _update_room_with_guard(room_id, "CLEANING")


def _update_room_to_inspecting(event):
    """Update room status to INSPECTING (with OCCUPIED guard)."""
    room_id = event["roomId"]
    return _update_room_with_guard(room_id, "INSPECTING")


def _update_room_to_available(event):
    """Update room status to AVAILABLE (with OCCUPIED guard)."""
    room_id = event["roomId"]
    return _update_room_with_guard(room_id, "AVAILABLE")


def _update_room_with_guard(room_id, new_status):
    """Update room status only if not OCCUPIED (stale task protection)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM rooms WHERE room_id = %s FOR UPDATE",
            [room_id],
        )
        room = cur.fetchone()
        if not room:
            logger.error("Room not found", room_id=room_id)
            return {"skipped": True, "reason": "ROOM_NOT_FOUND"}

        if room["status"] == "OCCUPIED":
            logger.warning(
                "OCCUPIED guard: skipping room status update",
                room_id=room_id,
                attempted_status=new_status,
            )
            return {"skipped": True, "reason": "OCCUPIED"}

        cur.execute(
            "UPDATE rooms SET status = %s, updated_at = now() WHERE room_id = %s",
            [new_status, room_id],
        )
        conn.commit()

    logger.info("Room status updated", room_id=room_id, new_status=new_status)
    return {"skipped": False, "newStatus": new_status}


def _record_cleaning_complete(event):
    """Record cleaning completion timestamp."""
    task_id = event["taskId"]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE housekeeping_tasks SET status = 'COMPLETED', "
            "completed_at = now(), updated_at = now() WHERE task_id = %s",
            [task_id],
        )
        conn.commit()
    return {"taskId": task_id, "status": "COMPLETED"}


def _record_inspection_complete(event):
    """Record inspection completion."""
    task_id = event["taskId"]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE housekeeping_tasks SET status = 'INSPECTED', "
            "inspected_at = now(), updated_at = now() WHERE task_id = %s",
            [task_id],
        )
        conn.commit()
    return {"taskId": task_id, "status": "INSPECTED"}

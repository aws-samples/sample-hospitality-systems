"""
PMS Night Audit Manual Trigger.

POST /audit/runs
Admin-only endpoint to manually trigger night audit for a specific date.
"""

import json
from datetime import date
from utils.logger import get_logger
from utils.response import ok, error, forbidden, server_error
from utils.validation import parse_body
from utils.tenant import require_groups, ForbiddenError

logger = get_logger("pms-night-audit")

# Import the worker handler directly. CodeUri is src/pms/night_audit/, so the
# sibling module is imported as 'worker' (no 'night_audit' package at runtime).
from worker import handler as audit_worker


@logger.inject_lambda_context
def handler(event, context):
    try:
        # Admin only
        require_groups(event, "Admin")

        body = parse_body(event) or {}
        audit_date = body.get("date", str(date.today()))

        # Validate date format
        try:
            from datetime import datetime
            datetime.strptime(audit_date, "%Y-%m-%d")
        except ValueError:
            return error(400, "VALIDATION_ERROR", "date must be YYYY-MM-DD format")

        # Run the audit worker with manual trigger
        result = audit_worker(
            {"auditDate": audit_date, "triggeredBy": "manual"},
            context,
        )

        return ok(result)

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error triggering night audit")
        return server_error()

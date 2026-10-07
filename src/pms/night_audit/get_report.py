"""
PMS Night Audit Report.

GET /audit/reports/{propertyId}?date=
Returns night audit metrics for a property on a given date.
"""

from datetime import date

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, verify_property_access
from utils.validation import validate_uuid

logger = get_logger("pms-night-audit")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin")

        property_id = validate_uuid(
            event.get("pathParameters", {}).get("propertyId"), "propertyId"
        )
        verify_property_access(event, property_id)

        params = event.get("queryStringParameters") or {}
        audit_date = params.get("date", str(date.today()))

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, audit_date, property_id, metrics, triggered_by, created_at "
                "FROM night_audit_runs "
                "WHERE property_id = %s AND audit_date = %s",
                [property_id, audit_date],
            )
            report = cur.fetchone()

        if not report:
            return error(404, "NOT_FOUND",
                        f"No audit report for property on {audit_date}")

        return ok({
            "runId": str(report["run_id"]),
            "auditDate": str(report["audit_date"]),
            "propertyId": str(report["property_id"]),
            "metrics": report["metrics"],
            "triggeredBy": report["triggered_by"],
            "createdAt": report["created_at"].isoformat(),
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error getting audit report")
        return server_error()

"""
PMS Void Folio.

POST /billing/folios/{folioId}/void
Void a folio and all its charges (manual cancellation).
Manager/Admin only.
"""

from utils.auth import get_user_id
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, verify_property_access
from utils.validation import parse_body, validate_uuid

logger = get_logger("pms-billing")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "Manager", "Admin")
        staff_user_id = get_user_id(event)

        folio_id = validate_uuid(
            event.get("pathParameters", {}).get("folioId"), "folioId"
        )

        body = parse_body(event) or {}
        reason = body.get("reason", "Manual void")

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT folio_id, property_id, status FROM folios WHERE folio_id = %s",
                [folio_id],
            )
            folio = cur.fetchone()
            if not folio:
                return error(404, "NOT_FOUND", "Folio not found")

            verify_property_access(event, str(folio["property_id"]))

            if folio["status"] != "OPEN":
                return error(409, "INVALID_STATE",
                            f"Can only void OPEN folios, current: {folio['status']}")

            # Void folio
            cur.execute(
                "UPDATE folios SET status = 'VOID', updated_at = now() WHERE folio_id = %s",
                [folio_id],
            )

            # Void all active charges
            cur.execute(
                "UPDATE charges SET status = 'VOIDED', voided_at = now(), voided_by = %s "
                "WHERE folio_id = %s AND status = 'ACTIVE'",
                [staff_user_id, folio_id],
            )

            conn.commit()

        logger.info("Folio voided", folio_id=folio_id, reason=reason, by=staff_user_id)

        return ok({
            "folioId": folio_id,
            "status": "VOID",
            "reason": reason,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error voiding folio")
        return server_error()

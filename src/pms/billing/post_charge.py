"""
PMS Post Charge to Folio.

POST /billing/folios/{folioId}/charges
Add a charge (SERVICE, ADJUSTMENT) to an open folio.
Manager/Admin only.
"""

import uuid

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

        folio_id = validate_uuid(
            event.get("pathParameters", {}).get("folioId"), "folioId"
        )

        body = parse_body(event)
        if not body:
            return error(400, "VALIDATION_ERROR", "Request body is required")

        charge_type = body.get("chargeType", "SERVICE")
        description = body.get("description", "")
        amount = body.get("amount")
        charge_date = body.get("chargeDate")

        # Validation
        if charge_type not in ("SERVICE", "ADJUSTMENT"):
            return error(400, "VALIDATION_ERROR", "chargeType must be SERVICE or ADJUSTMENT")
        if amount is None or not isinstance(amount, (int, float)) or amount == 0:
            return error(400, "VALIDATION_ERROR", "amount is required and must be non-zero")
        if not description or len(description) > 500:
            return error(400, "VALIDATION_ERROR", "description is required (max 500 chars)")

        with get_conn() as conn, conn.cursor() as cur:
            # Verify folio exists and is OPEN
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
                            f"Can only post charges to OPEN folios, current: {folio['status']}")

            # Create charge
            charge_id = str(uuid.uuid4())
            from datetime import date as date_type
            actual_date = charge_date or str(date_type.today())

            cur.execute(
                "INSERT INTO charges "
                "(charge_id, folio_id, charge_type, description, amount, charge_date) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [charge_id, folio_id, charge_type, description, amount, actual_date],
            )
            conn.commit()

        return ok({
            "chargeId": charge_id,
            "folioId": folio_id,
            "chargeType": charge_type,
            "description": description,
            "amount": amount,
            "chargeDate": actual_date,
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error posting charge")
        return server_error()

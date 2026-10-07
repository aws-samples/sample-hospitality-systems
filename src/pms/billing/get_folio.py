"""
PMS Get Folio Handler.

GET /billing/folios/{folioId}
Returns folio with all charges and payments.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import error, forbidden, ok, server_error
from utils.tenant import ForbiddenError, require_groups, verify_property_access
from utils.validation import validate_uuid

logger = get_logger("pms-billing")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        folio_id = validate_uuid(
            event.get("pathParameters", {}).get("folioId"), "folioId"
        )

        with get_conn() as conn, conn.cursor() as cur:
            # Get folio
            cur.execute(
                "SELECT f.folio_id, f.reservation_id, f.property_id, f.guest_id, "
                "f.check_in_date, f.check_out_date, f.status, "
                "f.subtotal, f.tax_amount, f.total_amount, "
                "f.payment_method, f.paid_at, f.created_at, "
                "g.first_name, g.last_name "
                "FROM folios f "
                "LEFT JOIN guests g ON f.guest_id = g.guest_id "
                "WHERE f.folio_id = %s",
                [folio_id],
            )
            folio = cur.fetchone()
            if not folio:
                return error(404, "NOT_FOUND", "Folio not found")

            verify_property_access(event, str(folio["property_id"]))

            # Get charges
            cur.execute(
                "SELECT charge_id, charge_type, description, amount, "
                "charge_date, status, voided_at, created_at "
                "FROM charges WHERE folio_id = %s ORDER BY charge_date, created_at",
                [folio_id],
            )
            charges = cur.fetchall()

            # Get payments
            cur.execute(
                "SELECT payment_id, amount, method, status, created_at "
                "FROM payments WHERE folio_id = %s ORDER BY created_at",
                [folio_id],
            )
            payments = cur.fetchall()

        return ok({
            "folio": {
                "folioId": str(folio["folio_id"]),
                "reservationId": str(folio["reservation_id"]),
                "propertyId": str(folio["property_id"]),
                "guestId": str(folio["guest_id"]),
                "guestName": f"{folio['first_name']} {folio['last_name']}",
                "checkInDate": str(folio["check_in_date"]),
                "checkOutDate": str(folio["check_out_date"]),
                "status": folio["status"],
                "subtotal": float(folio["subtotal"]) if folio["subtotal"] else None,
                "taxAmount": float(folio["tax_amount"]) if folio["tax_amount"] else None,
                "totalAmount": float(folio["total_amount"]) if folio["total_amount"] else None,
                "paymentMethod": folio["payment_method"],
                "paidAt": folio["paid_at"].isoformat() if folio["paid_at"] else None,
            },
            "charges": [
                {
                    "chargeId": str(c["charge_id"]),
                    "chargeType": c["charge_type"],
                    "description": c["description"],
                    "amount": float(c["amount"]),
                    "chargeDate": str(c["charge_date"]),
                    "status": c["status"],
                }
                for c in charges
            ],
            "payments": [
                {
                    "paymentId": str(p["payment_id"]),
                    "amount": float(p["amount"]),
                    "method": p["method"],
                    "status": p["status"],
                    "createdAt": p["created_at"].isoformat(),
                }
                for p in payments
            ],
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception:
        logger.exception("Error getting folio")
        return server_error()

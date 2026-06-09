"""
PMS Get Loyalty Transactions.

GET /loyalty/{guestId}/transactions?type=&from=&to=&page=&limit=
Returns paginated transaction history.
"""

from utils.logger import get_logger
from utils.database import get_conn
from utils.response import ok, error, forbidden, server_error
from utils.validation import validate_uuid
from utils.tenant import require_groups, ForbiddenError

logger = get_logger("pms-loyalty")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(event, "FrontDesk", "Manager", "Admin")

        guest_id = validate_uuid(
            event.get("pathParameters", {}).get("guestId"), "guestId"
        )

        params = event.get("queryStringParameters") or {}
        type_filter = params.get("type")  # EARN_STAY, REDEEM_NIGHT, ADJUSTMENT
        date_from = params.get("from")
        date_to = params.get("to")
        page = int(params.get("page", "1"))
        limit = min(int(params.get("limit", "20")), 100)
        offset = (page - 1) * limit

        # date_to end-of-day boundary (matches original semantics)
        date_to_bound = (date_to + "T23:59:59Z") if date_to else None

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Static queries; optional filters use NULL-guard predicates so the
                # SQL text never changes.  guest_id is always required (plain equality).
                # type_filter, date_from, date_to are optional (each bound twice).
                filter_params = [
                    guest_id,
                    type_filter, type_filter,
                    date_from, date_from,
                    date_to_bound, date_to_bound,
                ]

                cur.execute(
                    "SELECT COUNT(*) as total "
                    "FROM loyalty_transactions lt "
                    "WHERE lt.guest_id = %s "
                    "AND (%s::text IS NULL OR lt.transaction_type = %s::text) "
                    "AND (%s::timestamptz IS NULL OR lt.created_at >= %s::timestamptz) "
                    "AND (%s::timestamptz IS NULL OR lt.created_at <= %s::timestamptz)",
                    filter_params,
                )
                total = cur.fetchone()["total"]

                cur.execute(
                    "SELECT lt.transaction_id, lt.reservation_id, lt.transaction_type, "
                    "lt.points, lt.balance_after, lt.description, lt.created_at "
                    "FROM loyalty_transactions lt "
                    "WHERE lt.guest_id = %s "
                    "AND (%s::text IS NULL OR lt.transaction_type = %s::text) "
                    "AND (%s::timestamptz IS NULL OR lt.created_at >= %s::timestamptz) "
                    "AND (%s::timestamptz IS NULL OR lt.created_at <= %s::timestamptz) "
                    "ORDER BY lt.created_at DESC "
                    "LIMIT %s OFFSET %s",
                    filter_params + [limit, offset],
                )
                transactions = cur.fetchall()

        return ok({
            "transactions": [
                {
                    "transactionId": str(t["transaction_id"]),
                    "reservationId": str(t["reservation_id"]) if t["reservation_id"] else None,
                    "type": t["transaction_type"],
                    "points": t["points"],
                    "balanceAfter": t["balance_after"],
                    "description": t["description"],
                    "createdAt": t["created_at"].isoformat(),
                }
                for t in transactions
            ],
            "pagination": {"page": page, "limit": limit, "total": total},
        })

    except ForbiddenError as e:
        return forbidden(str(e))
    except ValueError as e:
        return error(400, 'VALIDATION_ERROR', str(e))
    except Exception as e:
        logger.exception("Error getting loyalty transactions")
        return server_error()

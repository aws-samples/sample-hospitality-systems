"""
Lambda handler for GET /guests/{guestId}/reservations.

Lists reservations belonging to a guest with optional status filtering
and pagination. Joins with properties to include the property name.
Results are ordered by check-in date descending (most recent first).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from utils.auth import get_claims
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, forbidden, not_found, ok, server_error
from utils.validation import validate_pagination, validate_uuid

logger = get_logger("guest")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def handler(event, context):
    """List reservations for a guest."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Extract path parameter
        guest_id = event.get("pathParameters", {}).get("guestId")
        if not guest_id or not validate_uuid(guest_id):
            return bad_request("A valid guestId path parameter is required.")

        # Verify ownership
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT guest_id, cognito_sub FROM guests WHERE guest_id = %s",
                    (guest_id,),
                )
                guest = cur.fetchone()

            if not guest:
                conn.commit()
                return not_found("Guest not found.")

            if guest["cognito_sub"] != cognito_sub:
                conn.commit()
                return forbidden("You do not have permission to access this resource.")

            # Query parameters
            params = event.get("queryStringParameters") or {}
            # status_filter is uppercased before binding (matches original)
            status_raw = params.get("status")
            status_filter = status_raw.upper() if status_raw else None

            pagination = validate_pagination(event)
            page = pagination["page"]
            limit = pagination["limit"]
            offset = pagination["offset"]

            # Static queries; guest_id is required (plain equality).
            # status_filter is optional (NULL-guarded, bound twice).
            filter_params = [guest_id, status_filter, status_filter]

            # Count total
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total "
                    "FROM reservations r "
                    "WHERE r.guest_id = %s "
                    "AND (%s::text IS NULL OR r.status = %s::text)",
                    filter_params,
                )
                total = cur.fetchone()["total"]

            # Fetch page with property name join
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT r.*, p.name AS property_name "
                    "FROM reservations r "
                    "LEFT JOIN properties p ON r.property_id = p.property_id "
                    "WHERE r.guest_id = %s "
                    "AND (%s::text IS NULL OR r.status = %s::text) "
                    "ORDER BY r.check_in_date DESC "
                    "LIMIT %s OFFSET %s",
                    filter_params + [limit, offset],
                )
                rows = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = [_serialize_row(row) for row in rows]
        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return ok(serialized, metadata={
            "pagination": {
                "page": page,
                "limit": limit,
                "total_items": total,
                "total_pages": total_pages,
            }
        })

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception:
        logger.exception("Error listing guest reservations")
        return server_error("Failed to list reservations.")

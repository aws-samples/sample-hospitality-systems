"""
Lambda handler for GET /reservations.

Lists all reservations for the authenticated guest with optional
status filtering and pagination. Results are ordered by check-in
date descending.
"""

from utils.logger import get_logger
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.response import ok, bad_request, server_error, transform_keys
from utils.auth import get_guest_id
from utils.validation import validate_pagination

logger = get_logger("crs")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, (UUID,)):
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


def _get_guest_id_from_sub(conn, cognito_sub):
    """Look up the guest_id from the cognito_sub claim."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT guest_id FROM guests WHERE cognito_sub = %s",
            (cognito_sub,),
        )
        row = cur.fetchone()
    if row:
        return str(row["guest_id"])
    return None


def handler(event, context):
    """List reservations for the authenticated guest."""
    try:
        # Auth required
        try:
            cognito_sub = get_guest_id(event)
        except (KeyError, TypeError):
            return bad_request("Authentication is required.")

        params = event.get("queryStringParameters") or {}
        # status_filter is uppercased before binding (matches original)
        status_raw = params.get("status")
        status_filter = status_raw.upper() if status_raw else None

        pagination = validate_pagination(event)
        page = pagination["page"]
        limit = pagination["limit"]
        offset = pagination["offset"]

        conn = get_conn()
        try:
            # Look up guest_id from cognito_sub
            guest_id = _get_guest_id_from_sub(conn, cognito_sub)
            if not guest_id:
                conn.rollback()
                return bad_request("Guest profile not found.")

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

            # Fetch page with property and room type names
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT r.*, "
                    "p.name AS property_name, "
                    "rt.name AS room_type_name, "
                    "r.total_after_tax AS total_amount, "
                    "r.currency_code AS currency "
                    "FROM reservations r "
                    "LEFT JOIN properties p ON p.property_id = r.property_id "
                    "LEFT JOIN room_types rt ON rt.room_type_id = r.room_type_id "
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

    except Exception as e:
        logger.exception("Error listing reservations")
        return server_error("Failed to list reservations.")

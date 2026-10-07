"""
Lambda handler for GET /properties.

Lists properties with optional filtering by city, state, featured status,
and active status. Results are ordered by featured status (descending)
then name (ascending) with pagination support.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import ok, server_error
from utils.validation import validate_pagination

logger = get_logger("property")


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


def handler(event, context):
    """List properties with optional filters and pagination."""
    try:
        params = event.get("queryStringParameters") or {}

        city = params.get("city")
        state = params.get("state")
        featured = params.get("featured")
        is_active_raw = params.get("is_active", "true")

        pagination = validate_pagination(event)
        page = pagination["page"]
        limit = pagination["limit"]
        offset = pagination["offset"]

        # Determine is_active filter value.
        # Original: if is_active != "false" => TRUE, else => FALSE.
        # We bind a bool and match exactly; never NULL so always a plain equality.
        is_active_val = is_active_raw.lower() != "false"

        # featured: True when "true"/"1", None (no filter) otherwise.
        if featured is not None and featured.lower() in ("true", "1"):
            featured_val = True
        else:
            featured_val = None

        # city / state: None means no filter (NULL-guarded below).
        city_lower = city.lower() if city else None
        state_lower = state.lower() if state else None

        # Static queries; optional filters use NULL-guard predicates.
        # is_active is always bound (never NULL — original always set it one way).
        # city/state/featured are optional (each bound twice for NULL-guard).
        filter_params = [
            is_active_val,
            city_lower, city_lower,
            state_lower, state_lower,
            featured_val, featured_val,
        ]

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total "
                    "FROM properties p "
                    "WHERE p.is_active = %s::bool "
                    "AND (%s::text IS NULL OR LOWER(p.city) = %s::text) "
                    "AND (%s::text IS NULL OR LOWER(p.state) = %s::text) "
                    "AND (%s::bool IS NULL OR p.is_featured = %s::bool)",
                    filter_params,
                )
                total = cur.fetchone()["total"]

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.* "
                    "FROM properties p "
                    "WHERE p.is_active = %s::bool "
                    "AND (%s::text IS NULL OR LOWER(p.city) = %s::text) "
                    "AND (%s::text IS NULL OR LOWER(p.state) = %s::text) "
                    "AND (%s::bool IS NULL OR p.is_featured = %s::bool) "
                    "ORDER BY p.is_featured DESC, p.name ASC "
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

    except Exception:
        logger.exception("Error listing properties")
        return server_error("Failed to list properties.")

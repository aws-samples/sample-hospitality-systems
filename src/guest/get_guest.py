"""
Lambda handler for GET /guests/{guestId}.

Retrieves a guest profile by ID. Only the owning guest (matched via
cognito_sub from JWT) may access their own profile.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from utils.auth import get_claims
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import bad_request, forbidden, not_found, ok, server_error
from utils.validation import validate_uuid

logger = get_logger("guest")

# Fields to exclude from the response for privacy
SENSITIVE_FIELDS = {"identity_doc_type", "identity_doc_number", "identity_doc_expiry"}


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
    """Serialize all values in a row dict, excluding sensitive fields."""
    return {
        k: _serialize(v) for k, v in row.items()
        if k not in SENSITIVE_FIELDS
    }


def handler(event, context):
    """Get a guest profile by ID."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Extract path parameter
        guest_id = event.get("pathParameters", {}).get("guestId")
        if not guest_id or not validate_uuid(guest_id):
            return bad_request("A valid guestId path parameter is required.")

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM guests WHERE guest_id = %s",
                    (guest_id,),
                )
                guest = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not guest:
            return not_found("Guest not found.")

        # Owner-only access: verify cognito_sub matches
        if guest["cognito_sub"] != cognito_sub:
            return forbidden("You do not have permission to access this resource.")

        serialized = _serialize_row(guest)
        return ok(serialized)

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception:
        logger.exception("Error retrieving guest")
        return server_error("Failed to retrieve guest.")

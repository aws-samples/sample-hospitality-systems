"""
Lambda handler for PUT /guests/{guestId}.

Updates an existing guest profile. Only the owning guest may update
their own profile. Email and cognito_sub cannot be changed.
"""

import json
from utils.logger import get_logger
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from utils.database import get_conn
from utils.response import ok, not_found, forbidden, bad_request, server_error
from utils.auth import get_claims
from utils.events import publish_event
from utils.validation import parse_body, validate_uuid

logger = get_logger("guest")

# Fields that can be updated via this endpoint
ALLOWED_FIELDS = {
    "firstName": "first_name",
    "lastName": "last_name",
    "phone": "phone",
    "dateOfBirth": "date_of_birth",
    "nationality": "nationality",
    "language": "language",
    "addressLine1": "address_line1",
    "addressLine2": "address_line2",
    "city": "city",
    "state": "state",
    "postalCode": "postal_code",
    "country": "country",
    "preferences": "preferences",
    "commPrefs": "comm_prefs",
}

# Fields stored as JSONB in the database
JSONB_FIELDS = {"preferences", "comm_prefs"}


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
    """Update an existing guest profile."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Extract path parameter
        guest_id = event.get("pathParameters", {}).get("guestId")
        if not guest_id or not validate_uuid(guest_id):
            return bad_request("A valid guestId path parameter is required.")

        # Parse body
        body = parse_body(event)
        if not body:
            return bad_request("Request body is required.")

        # Reject attempts to change immutable fields
        if "email" in body or "cognitoSub" in body:
            return bad_request("Cannot change email or cognitoSub.")

        conn = get_conn()
        try:
            # Fetch the current row so unspecified fields keep their values.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM guests WHERE guest_id = %s",
                    (guest_id,),
                )
                existing = cur.fetchone()

            if not existing:
                conn.commit()
                return not_found("Guest not found.")

            if existing["cognito_sub"] != cognito_sub:
                conn.commit()
                return forbidden("You do not have permission to update this resource.")

            # Reject a request that provides none of the updatable fields.
            if not any(camel_key in body for camel_key in ALLOWED_FIELDS):
                conn.commit()
                return bad_request("No valid fields provided for update.")

            # Merge in Python: each column takes the request value when the field
            # is present in the body, otherwise its current value (so absent
            # fields are preserved; an explicit null clears the field). The UPDATE
            # below is a fixed string literal — every value is bound as a
            # parameter, no SQL is assembled from strings. The bound-value order
            # MUST match the column order in the static statement; both are driven
            # by ALLOWED_FIELDS iteration order.
            def _merged(camel_key, db_col):
                value = body[camel_key] if camel_key in body else existing[db_col]
                if db_col in JSONB_FIELDS:
                    return json.dumps(value) if value is not None else None
                return value

            values = [_merged(ck, col) for ck, col in ALLOWED_FIELDS.items()]
            values.append(datetime.now(timezone.utc))  # updated_at
            values.append(guest_id)  # WHERE

            # Static UPDATE. Column order matches ALLOWED_FIELDS (first_name,
            # last_name, phone, date_of_birth, nationality, language,
            # address_line_1, address_line_2, city, state, postal_code, country,
            # preferences, comm_prefs), then updated_at.
            update_sql = """
                UPDATE guests SET
                    first_name = %s,
                    last_name = %s,
                    phone = %s,
                    date_of_birth = %s,
                    nationality = %s,
                    language = %s,
                    address_line1 = %s,
                    address_line2 = %s,
                    city = %s,
                    state = %s,
                    postal_code = %s,
                    country = %s,
                    preferences = %s::jsonb,
                    comm_prefs = %s::jsonb,
                    updated_at = %s
                WHERE guest_id = %s
                RETURNING *
            """

            with conn.cursor() as cur:
                cur.execute(update_sql, values)
                updated_guest = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(updated_guest)

        # Publish event
        changed_fields = [k for k in ALLOWED_FIELDS if k in body]
        publish_event(
            source="anycompany.guest",
            detail_type="guest.updated",
            detail={
                "guestId": guest_id,
                "updatedFields": changed_fields,
            },
        )

        return ok(serialized)

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception as e:
        logger.exception("Error updating guest")
        return server_error("Failed to update guest.")

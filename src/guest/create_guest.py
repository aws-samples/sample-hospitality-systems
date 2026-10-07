"""
Lambda handler for POST /guests.

Creates a new guest profile linked to the authenticated Cognito user.
Also creates a corresponding Stripe customer for future payment operations.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from utils.auth import get_claims
from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.response import created, error, ok, server_error
from utils.stripe_client import create_customer
from utils.validation import parse_body, require_fields

logger = get_logger("guest")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def handler(event, context):
    """Create a new guest profile."""
    try:
        # Auth required
        try:
            claims = get_claims(event)
            cognito_sub = claims["sub"]
        except (KeyError, TypeError):
            return error(401, "UNAUTHORIZED", "Authentication required.")

        # Parse and validate body
        body = parse_body(event)
        field_error = require_fields(body, ["firstName", "lastName", "email"])
        if field_error:
            return field_error

        first_name = body["firstName"]
        last_name = body["lastName"]
        email = body["email"]
        phone = body.get("phone")
        date_of_birth = body.get("dateOfBirth")
        preferences = body.get("preferences")
        comm_prefs = body.get("commPrefs")

        conn = get_conn()
        try:
            # Check if guest already exists with this cognito_sub
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM guests WHERE cognito_sub = %s",
                    (cognito_sub,),
                )
                existing = cur.fetchone()

            if existing:
                # Backfill empty name fields if the request provides them
                needs_update = (
                    (not existing["first_name"] and first_name)
                    or (not existing["last_name"] and last_name)
                )
                if needs_update:
                    now = datetime.now(UTC)
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE guests
                            SET first_name = COALESCE(NULLIF(first_name, ''), %s),
                                last_name  = COALESCE(NULLIF(last_name, ''), %s),
                                updated_at = %s
                            WHERE guest_id = %s
                            RETURNING *
                            """,
                            (first_name, last_name, now, existing["guest_id"]),
                        )
                        existing = cur.fetchone()
                conn.commit()
                return ok(_serialize_row(existing))

            # Create Stripe customer
            full_name = f"{first_name} {last_name}"
            stripe_customer = create_customer(
                email=email,
                name=full_name,
                metadata={"cognito_sub": cognito_sub},
            )
            stripe_customer_id = stripe_customer.id

            # Insert guest record
            guest_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO guests (
                        guest_id, cognito_sub, stripe_customer_id,
                        first_name, last_name, email, phone,
                        date_of_birth, preferences, comm_prefs,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        guest_id, cognito_sub, stripe_customer_id,
                        first_name, last_name, email, phone,
                        date_of_birth,
                        __import__("json").dumps(preferences) if preferences else None,
                        __import__("json").dumps(comm_prefs) if comm_prefs else None,
                        now, now,
                    ),
                )
                guest = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = _serialize_row(guest)

        # Publish event
        publish_event(
            source="anycompany.guest",
            detail_type="guest.created",
            detail={
                "guestId": guest_id,
                "email": email,
                "stripeCustomerId": stripe_customer_id,
            },
        )

        return created(serialized)

    except Exception:
        logger.exception("Error creating guest")
        return server_error("Failed to create guest.")

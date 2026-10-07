"""
Lambda handler for GET /payment-methods.

Lists all stored payment methods for the authenticated guest.
"""

import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from utils.auth import get_claims
from utils.database import get_conn
from utils.logger import get_logger
from utils.response import not_found, ok, server_error

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


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
    """List payment methods for the authenticated guest."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        conn = get_conn()
        try:
            # Look up guest by cognito_sub
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT guest_id FROM guests WHERE cognito_sub = %s",
                    (cognito_sub,),
                )
                guest = cur.fetchone()

            if not guest:
                conn.commit()
                return not_found("Guest profile not found.")

            guest_id = str(guest["guest_id"])

            # Fetch stored payment methods
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payment_method_id, guest_id, stripe_payment_method_id,
                           brand, last4, exp_month, exp_year,
                           is_default, created_at, updated_at
                    FROM stored_payment_methods
                    WHERE guest_id = %s
                    ORDER BY is_default DESC, created_at DESC
                    """,
                    (guest_id,),
                )
                rows = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        serialized = [_serialize_row(row) for row in rows]
        return ok(serialized)

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception:
        logger.exception("Error listing payment methods")
        return server_error("Failed to list payment methods.")

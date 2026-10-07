"""
Lambda handler for GET /payments/{paymentId}.

Retrieves a payment authorization along with its associated captures
and refunds. Only the owning guest may access their payment details.
"""

from utils.logger import get_logger
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from utils.database import get_conn
from utils.response import ok, not_found, forbidden, bad_request, server_error
from utils.auth import get_claims
from utils.validation import validate_uuid

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
    """Get payment details by authorization ID."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Extract path parameter
        payment_id = event.get("pathParameters", {}).get("paymentId")
        if not payment_id or not validate_uuid(payment_id):
            return bad_request("A valid paymentId path parameter is required.")

        conn = get_conn()
        try:
            # Get authorization with guest ownership check
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pa.*, g.cognito_sub
                    FROM payment_authorizations pa
                    JOIN guests g ON pa.guest_id = g.guest_id
                    WHERE pa.authorization_id = %s
                    """,
                    (payment_id,),
                )
                auth_record = cur.fetchone()

            if not auth_record:
                conn.commit()
                return not_found("Payment not found.")

            if auth_record["cognito_sub"] != cognito_sub:
                conn.commit()
                return forbidden("You do not have permission to access this payment.")

            # Remove cognito_sub from response
            del auth_record["cognito_sub"]

            # Get associated captures
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM payment_captures
                    WHERE authorization_id = %s
                    ORDER BY created_at DESC
                    """,
                    (payment_id,),
                )
                captures = cur.fetchall()

            # Get associated refunds (refunds FK to a capture, which FKs to
            # the authorization).
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pr.*
                    FROM payment_refunds pr
                    JOIN payment_captures pc ON pr.capture_id = pc.capture_id
                    WHERE pc.authorization_id = %s
                    ORDER BY pr.created_at DESC
                    """,
                    (payment_id,),
                )
                refunds = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        payment_data = _serialize_row(auth_record)
        payment_data["captures"] = [_serialize_row(c) for c in captures]
        payment_data["refunds"] = [_serialize_row(r) for r in refunds]

        return ok(payment_data)

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception as e:
        logger.exception("Error retrieving payment")
        return server_error("Failed to retrieve payment.")

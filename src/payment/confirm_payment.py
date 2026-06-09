"""
Lambda handler for POST /payments/confirm.

Captures a previously authorized Stripe PaymentIntent and records
the capture in the database. Publishes a payment.captured event.
"""

from utils.logger import get_logger
import os
import uuid
from datetime import datetime, timezone

from utils.database import get_conn
from utils.response import ok, bad_request, not_found, server_error
from utils.auth import get_claims
from utils.events import publish_event
from utils.validation import parse_body, require_fields
from utils.stripe_client import capture_payment

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


def handler(event, context):
    """Capture a previously authorized payment."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Parse and validate body
        body = parse_body(event)
        field_error = require_fields(body, ["paymentIntentId", "authorizationId"])
        if field_error:
            return field_error

        payment_intent_id = body["paymentIntentId"]
        authorization_id = body["authorizationId"]

        conn = get_conn()
        try:
            # Verify authorization exists and belongs to the caller
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pa.*, g.cognito_sub
                    FROM payment_authorizations pa
                    JOIN guests g ON pa.guest_id = g.guest_id
                    WHERE pa.authorization_id = %s
                      AND pa.stripe_payment_intent_id = %s
                    """,
                    (authorization_id, payment_intent_id),
                )
                auth_record = cur.fetchone()

            if not auth_record:
                conn.commit()
                return not_found("Payment authorization not found.")

            if auth_record["cognito_sub"] != cognito_sub:
                conn.commit()
                return bad_request("You do not have permission to capture this payment.")

            if auth_record["status"] == "CAPTURED":
                conn.commit()
                return bad_request("This payment has already been captured.")

            # Capture via Stripe
            captured_intent = capture_payment(payment_intent_id)

            # Update authorization status
            now = datetime.now(timezone.utc)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE payment_authorizations
                    SET status = 'CAPTURED', updated_at = %s
                    WHERE authorization_id = %s
                    """,
                    (now, authorization_id),
                )

            # Insert capture record
            capture_id = str(uuid.uuid4())
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payment_captures (
                        capture_id, authorization_id, stripe_payment_intent_id,
                        amount_cents, currency, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        capture_id, authorization_id, payment_intent_id,
                        auth_record["amount_cents"], auth_record["currency"],
                        "SUCCEEDED", now,
                    ),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Publish event
        publish_event(
            source="anycompany.payments",
            detail_type="payment.captured",
            detail={
                "authorizationId": authorization_id,
                "captureId": capture_id,
                "guestId": str(auth_record["guest_id"]),
                "reservationId": str(auth_record["reservation_id"]),
                "amountCents": auth_record["amount_cents"],
                "currency": auth_record["currency"],
                "stripePaymentIntentId": payment_intent_id,
            },
        )

        return ok({
            "capture_id": capture_id,
            "authorization_id": authorization_id,
            "stripe_payment_intent_id": payment_intent_id,
            "amount_cents": auth_record["amount_cents"],
            "currency": auth_record["currency"],
            "status": "SUCCEEDED",
            "captured_at": now.isoformat(),
        })

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception as e:
        logger.exception("Error confirming payment")
        return server_error("Failed to confirm payment.")

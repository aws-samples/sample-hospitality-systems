"""
Lambda handler for POST /payments/{paymentId}/refund.

Creates a full or partial refund against a captured payment via Stripe.
Records the refund in the database and publishes a payment.refunded event.
"""

from utils.logger import get_logger
import os
import uuid
from datetime import datetime, timezone

from utils.database import get_conn
from utils.response import ok, bad_request, not_found, forbidden, server_error
from utils.auth import get_claims
from utils.events import publish_event
from utils.validation import parse_body, require_fields, validate_uuid
from utils.stripe_client import create_refund

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


def handler(event, context):
    """Refund a captured payment."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Extract path parameter
        payment_id = event.get("pathParameters", {}).get("paymentId")
        if not payment_id or not validate_uuid(payment_id):
            return bad_request("A valid paymentId path parameter is required.")

        # Parse body
        body = parse_body(event)
        field_error = require_fields(body, ["reason"])
        if field_error:
            return field_error

        refund_amount = body.get("amount")  # Optional, in dollars
        reason = body["reason"]

        conn = get_conn()
        try:
            # Get authorization and verify ownership
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
                return forbidden("You do not have permission to refund this payment.")

            if auth_record["status"] != "CAPTURED":
                conn.commit()
                return bad_request("Only captured payments can be refunded.")

            # Get captures to verify total captured amount
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(amount_cents), 0) AS total_captured
                    FROM payment_captures
                    WHERE authorization_id = %s AND status = 'SUCCEEDED'
                    """,
                    (payment_id,),
                )
                capture_row = cur.fetchone()
                total_captured = capture_row["total_captured"]

            # Get existing refunds to check remaining refundable amount
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(amount_cents), 0) AS total_refunded
                    FROM payment_refunds
                    WHERE authorization_id = %s AND status = 'SUCCEEDED'
                    """,
                    (payment_id,),
                )
                refund_row = cur.fetchone()
                total_refunded = refund_row["total_refunded"]

            refundable_cents = total_captured - total_refunded

            if refundable_cents <= 0:
                conn.commit()
                return bad_request("This payment has already been fully refunded.")

            # Determine refund amount in cents
            if refund_amount is not None:
                try:
                    refund_amount = float(refund_amount)
                except (ValueError, TypeError):
                    conn.commit()
                    return bad_request("Amount must be a valid number.")

                if refund_amount <= 0:
                    conn.commit()
                    return bad_request("Refund amount must be greater than zero.")

                refund_amount_cents = int(round(refund_amount * 100))

                if refund_amount_cents > refundable_cents:
                    conn.commit()
                    return bad_request(
                        f"Refund amount exceeds refundable balance. "
                        f"Maximum refundable: ${refundable_cents / 100:.2f}"
                    )
            else:
                refund_amount_cents = refundable_cents

            # Map reason to Stripe-accepted values if possible
            stripe_reason = None
            reason_lower = reason.lower()
            if reason_lower in ("duplicate", "fraudulent", "requested_by_customer"):
                stripe_reason = reason_lower

            # Create refund via Stripe
            stripe_refund = create_refund(
                payment_intent_id=auth_record["stripe_payment_intent_id"],
                amount_cents=refund_amount_cents,
                reason=stripe_reason,
            )

            # Insert refund record
            refund_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payment_refunds (
                        refund_id, authorization_id, stripe_refund_id,
                        amount_cents, currency, reason, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        refund_id, payment_id, stripe_refund.id,
                        refund_amount_cents, auth_record["currency"],
                        reason, "SUCCEEDED", now,
                    ),
                )

            # If fully refunded, update authorization status
            new_total_refunded = total_refunded + refund_amount_cents
            if new_total_refunded >= total_captured:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE payment_authorizations
                        SET status = 'REFUNDED', updated_at = %s
                        WHERE authorization_id = %s
                        """,
                        (now, payment_id),
                    )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Publish event
        publish_event(
            source="anycompany.payments",
            detail_type="payment.refunded",
            detail={
                "refundId": refund_id,
                "authorizationId": payment_id,
                "guestId": str(auth_record["guest_id"]),
                "reservationId": str(auth_record["reservation_id"]),
                "amountCents": refund_amount_cents,
                "currency": auth_record["currency"],
                "reason": reason,
                "stripeRefundId": stripe_refund.id,
            },
        )

        return ok({
            "refund_id": refund_id,
            "authorization_id": payment_id,
            "stripe_refund_id": stripe_refund.id,
            "amount_cents": refund_amount_cents,
            "currency": auth_record["currency"],
            "reason": reason,
            "status": "SUCCEEDED",
            "refunded_at": now.isoformat(),
        })

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception as e:
        logger.exception("Error processing refund")
        return server_error("Failed to process refund.")

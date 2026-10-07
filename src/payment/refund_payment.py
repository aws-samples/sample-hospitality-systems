"""
Lambda handler for POST /payments/{paymentId}/refund.

Creates a full or partial refund against a captured payment via Stripe.
Records the refund in the database and publishes a payment.refunded event.
"""

import os
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from utils.auth import get_claims
from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger
from utils.response import bad_request, forbidden, not_found, ok, server_error
from utils.stripe_client import create_refund
from utils.validation import parse_body, require_fields, validate_uuid

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")

# Allowed values for the payment_refunds.reason CHECK constraint.
ALLOWED_REFUND_REASONS = {
    "EARLY_DEPARTURE",
    "SERVICE_RECOVERY",
    "BILLING_ERROR",
    "CANCELLATION",
}
# Stripe-accepted refund reasons (a distinct, smaller vocabulary).
STRIPE_REFUND_REASONS = {"duplicate", "fraudulent", "requested_by_customer"}


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

        # reason must satisfy the payment_refunds.reason CHECK constraint.
        reason = str(reason).upper()
        if reason not in ALLOWED_REFUND_REASONS:
            return bad_request(
                "reason must be one of: "
                + ", ".join(sorted(ALLOWED_REFUND_REASONS))
            )

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

            # Get captures to verify total captured amount. Amounts are stored
            # in dollars (NUMERIC); refunds FK to a capture, so also grab the
            # most recent capture id to attach the refund to.
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(captured_amount), 0) AS total_captured,
                        MAX(capture_id::text)            AS any_capture_id
                    FROM payment_captures
                    WHERE authorization_id = %s
                    """,
                    (payment_id,),
                )
                capture_row = cur.fetchone()
                total_captured = Decimal(str(capture_row["total_captured"]))
                capture_id = capture_row["any_capture_id"]

            if not capture_id:
                conn.commit()
                return bad_request("No capture found for this payment.")

            # Get existing succeeded refunds (joined via capture) to check the
            # remaining refundable amount.
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(pr.amount), 0) AS total_refunded
                    FROM payment_refunds pr
                    JOIN payment_captures pc ON pr.capture_id = pc.capture_id
                    WHERE pc.authorization_id = %s AND pr.status = 'SUCCEEDED'
                    """,
                    (payment_id,),
                )
                refund_row = cur.fetchone()
                total_refunded = Decimal(str(refund_row["total_refunded"]))

            refundable = total_captured - total_refunded

            if refundable <= 0:
                conn.commit()
                return bad_request("This payment has already been fully refunded.")

            # Determine refund amount in dollars
            if refund_amount is not None:
                try:
                    refund_dollars = Decimal(str(refund_amount))
                except (ValueError, TypeError, InvalidOperation):
                    conn.commit()
                    return bad_request("Amount must be a valid number.")

                if refund_dollars <= 0:
                    conn.commit()
                    return bad_request("Refund amount must be greater than zero.")

                refund_dollars = refund_dollars.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                if refund_dollars > refundable:
                    conn.commit()
                    return bad_request(
                        f"Refund amount exceeds refundable balance. "
                        f"Maximum refundable: ${refundable:.2f}"
                    )
            else:
                refund_dollars = refundable

            # Convert to cents only at the Stripe boundary.
            refund_amount_cents = int((refund_dollars * 100).to_integral_value(rounding=ROUND_HALF_UP))

            # Create refund via Stripe (Stripe uses its own reason vocabulary).
            stripe_refund = create_refund(
                payment_intent_id=auth_record["stripe_payment_intent_id"],
                amount_cents=refund_amount_cents,
                reason=None,
            )

            # Insert refund record (FK to capture; amount in dollars)
            refund_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payment_refunds (
                        refund_id, capture_id, stripe_refund_id,
                        amount, reason, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        refund_id, capture_id, stripe_refund.id,
                        refund_dollars, reason, "SUCCEEDED", now,
                    ),
                )

            # If fully refunded, void the authorization (REFUNDED is not an
            # allowed authorization status; VOIDED signals no further capture).
            new_total_refunded = total_refunded + refund_dollars
            if new_total_refunded >= total_captured:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE payment_authorizations
                        SET status = 'VOIDED', updated_at = %s
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
    except Exception:
        logger.exception("Error processing refund")
        return server_error("Failed to process refund.")

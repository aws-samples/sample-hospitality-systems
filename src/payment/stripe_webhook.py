"""
Lambda handler for POST /webhooks/stripe.

Processes incoming Stripe webhook events. This is a public endpoint
(no JWT auth) -- authentication is performed by verifying the Stripe
webhook signature. Handles payment_intent.succeeded,
payment_intent.payment_failed, and charge.refunded events.
"""

import json
import os
import time
from datetime import datetime, timezone

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import ok, bad_request, server_error
from utils.stripe_client import get_stripe, verify_webhook_signature

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")

# Module-level cache for the webhook signing secret. The handler runs on every
# Stripe webhook delivery; fetching from Secrets Manager on each invocation adds
# latency, cost, and an extra failure mode (the endpoint would be a cheap target
# for flooding without rate-limiting). Cache the secret in a warm-container global
# with a short TTL so it survives across invocations but still picks up a rotated
# value within a few minutes.
_SECRET_CACHE_TTL_SECONDS = 300
_cached_webhook_secret = None
_cached_at = 0.0
_secrets_client = None


def _get_webhook_secret(force_refresh=False):
    """Return the Stripe webhook signing secret, cached for a short TTL.

    On a signature-verification failure the caller can pass force_refresh=True to
    bypass the cache once, covering the case where the secret was just rotated.
    """
    global _cached_webhook_secret, _cached_at, _secrets_client

    now = time.monotonic()
    if (
        not force_refresh
        and _cached_webhook_secret is not None
        and (now - _cached_at) < _SECRET_CACHE_TTL_SECONDS
    ):
        return _cached_webhook_secret

    import boto3

    if _secrets_client is None:
        _secrets_client = boto3.client("secretsmanager")

    secret_arn = os.environ.get("STRIPE_WEBHOOK_SECRET_ARN", stripe_secret_arn)
    response = _secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])
    value = secret.get("stripe_webhook_secret", secret.get("webhook_secret", ""))

    _cached_webhook_secret = value
    _cached_at = now
    return value


def handler(event, context):
    """Process Stripe webhook events."""
    try:
        # Get raw body and signature header
        raw_body = event.get("body", "")
        headers = event.get("headers", {})

        # Header keys may be lowercased by API Gateway
        sig_header = headers.get("Stripe-Signature") or headers.get("stripe-signature")

        if not sig_header:
            return bad_request("Missing Stripe-Signature header.")

        if not raw_body:
            return bad_request("Empty request body.")

        # Verify webhook signature. Use the cached secret first; if verification
        # fails, retry once with a forced refresh in case the secret was just
        # rotated and the cached copy is stale.
        try:
            stripe_event = verify_webhook_signature(
                raw_body, sig_header, _get_webhook_secret()
            )
        except Exception:
            try:
                stripe_event = verify_webhook_signature(
                    raw_body, sig_header, _get_webhook_secret(force_refresh=True)
                )
            except Exception as e:
                logger.warning("Webhook signature verification failed", error=str(e))
                return bad_request("Invalid webhook signature.")

        event_type = stripe_event.type
        data_object = stripe_event.data.object
        now = datetime.now(timezone.utc)

        logger.info("Processing Stripe webhook event", event_type=event_type)

        conn = get_conn()
        try:
            if event_type == "payment_intent.succeeded":
                _handle_payment_succeeded(conn, data_object, now)

            elif event_type == "payment_intent.payment_failed":
                _handle_payment_failed(conn, data_object, now)

            elif event_type == "charge.refunded":
                _handle_charge_refunded(conn, data_object, now)

            else:
                logger.info("Unhandled Stripe event type", event_type=event_type)

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return ok({"received": True, "event_type": event_type})

    except Exception as e:
        logger.exception("Error processing Stripe webhook")
        return server_error("Webhook processing failed.")


def _handle_payment_succeeded(conn, data_object, now):
    """Handle payment_intent.succeeded event.

    Updates the payment authorization status to AUTHORIZED when the
    PaymentIntent succeeds (customer has confirmed, awaiting capture).
    """
    payment_intent_id = data_object.id
    if not payment_intent_id:
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE payment_authorizations
            SET status = 'AUTHORIZED', updated_at = %s
            WHERE stripe_payment_intent_id = %s
              AND status IN ('REQUIRES_CONFIRMATION', 'PENDING')
            """,
            (now, payment_intent_id),
        )
        updated = cur.rowcount

    if updated:
        logger.info(
            "Payment authorization updated to AUTHORIZED",
            payment_intent_id=payment_intent_id,
        )


def _handle_payment_failed(conn, data_object, now):
    """Handle payment_intent.payment_failed event.

    Updates the payment authorization status to FAILED.
    """
    payment_intent_id = data_object.id
    if not payment_intent_id:
        return

    last_error = getattr(data_object, "last_payment_error", None)
    failure_message = last_error.message if last_error else ""

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE payment_authorizations
            SET status = 'FAILED', updated_at = %s
            WHERE stripe_payment_intent_id = %s
              AND status NOT IN ('CAPTURED', 'REFUNDED')
            """,
            (now, payment_intent_id),
        )
        updated = cur.rowcount

    if updated:
        logger.info(
            "Payment authorization updated to FAILED",
            payment_intent_id=payment_intent_id,
            failure_message=failure_message,
        )


def _handle_charge_refunded(conn, data_object, now):
    """Handle charge.refunded event.

    Updates refund records based on the Stripe charge refund data.
    """
    payment_intent_id = data_object.payment_intent
    if not payment_intent_id:
        return

    refunds_obj = getattr(data_object, "refunds", None)
    refunds = refunds_obj.data if refunds_obj else []

    for refund in refunds:
        stripe_refund_id = refund.id
        if not stripe_refund_id:
            continue

        status = refund.status or ""
        db_status = "SUCCEEDED" if status == "succeeded" else "FAILED"

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE payment_refunds
                SET status = %s
                WHERE stripe_refund_id = %s
                """,
                (db_status, stripe_refund_id),
            )

    logger.info(
        "Processed charge.refunded",
        payment_intent_id=payment_intent_id,
        refund_count=len(refunds),
    )

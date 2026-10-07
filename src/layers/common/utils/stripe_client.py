"""
Stripe wrapper for AnyCompany Hotel platform.

Provides a thin abstraction over the Stripe SDK for common hotel
payment operations: customer creation, PaymentIntent with manual
capture (for pre-auth/hold flows), capture, refund, and webhook
signature verification.

All monetary amounts are in cents (e.g., $150.00 = 15000).
"""

import json
import os
from typing import Any

import boto3
import stripe

_cached_api_key: str | None = None


def _get_stripe_secret() -> str:
    """
    Retrieve the Stripe secret API key from AWS Secrets Manager.
    Caches the key for the lifetime of the Lambda execution context.
    """
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    secret_arn = os.environ["STRIPE_SECRET_ARN"]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])
    _cached_api_key = secret["api_key"]
    return _cached_api_key


def get_stripe() -> stripe:
    """
    Initialize and return the stripe module configured with the secret key.

    The API key is loaded from Secrets Manager on first call and cached
    for subsequent calls within the same Lambda execution context.

    Returns:
        The configured stripe module.
    """
    stripe.api_key = _get_stripe_secret()
    return stripe


def create_customer(
    email: str,
    name: str,
    metadata: dict[str, str] | None = None,
) -> stripe.Customer:
    """
    Create a Stripe Customer.

    Args:
        email: Customer email address.
        name: Customer full name.
        metadata: Optional key-value metadata to attach to the customer.

    Returns:
        The created Stripe Customer object.
    """
    s = get_stripe()
    params: dict[str, Any] = {
        "email": email,
        "name": name,
    }
    if metadata:
        params["metadata"] = metadata

    return s.Customer.create(**params)


def create_payment_intent(
    amount_cents: int,
    currency: str,
    customer_id: str,
    metadata: dict[str, str] | None = None,
    payment_method: str | None = None,
    confirm: bool = False,
) -> stripe.PaymentIntent:
    """
    Create a Stripe PaymentIntent with manual capture.

    Uses capture_method='manual' to support the hotel pre-authorization
    flow: authorize at booking, capture at check-out/settlement.

    Args:
        amount_cents: Amount in cents (e.g., 15000 for $150.00).
        currency: Three-letter ISO currency code (e.g., "usd").
        customer_id: Stripe Customer ID to associate the payment with.
        metadata: Optional key-value metadata (e.g., reservation_id).
        payment_method: Optional Stripe PaymentMethod ID to attach and confirm.
        confirm: If True, confirm the intent immediately (requires payment_method).

    Returns:
        The created Stripe PaymentIntent object.
    """
    s = get_stripe()
    params: dict[str, Any] = {
        "amount": amount_cents,
        "currency": currency.lower(),
        "customer": customer_id,
        "capture_method": "manual",
    }
    if metadata:
        params["metadata"] = metadata
    if payment_method:
        params["payment_method"] = payment_method
    if confirm:
        params["confirm"] = True

    return s.PaymentIntent.create(**params)


def capture_payment(
    payment_intent_id: str,
    amount_cents: int | None = None,
) -> stripe.PaymentIntent:
    """
    Capture a previously authorized PaymentIntent.

    If amount_cents is provided, a partial capture is performed.
    Otherwise, the full authorized amount is captured.

    Args:
        payment_intent_id: The PaymentIntent ID to capture (pi_...).
        amount_cents: Optional amount to capture in cents. If None,
                      captures the full authorized amount.

    Returns:
        The captured Stripe PaymentIntent object.
    """
    s = get_stripe()
    params: dict[str, Any] = {}
    if amount_cents is not None:
        params["amount_to_capture"] = amount_cents

    return s.PaymentIntent.capture(payment_intent_id, **params)


def create_refund(
    payment_intent_id: str,
    amount_cents: int | None = None,
    reason: str | None = None,
) -> stripe.Refund:
    """
    Create a refund against a PaymentIntent.

    If amount_cents is provided, a partial refund is created.
    Otherwise, the full captured amount is refunded.

    Args:
        payment_intent_id: The PaymentIntent ID to refund (pi_...).
        amount_cents: Optional amount to refund in cents. If None,
                      refunds the full captured amount.
        reason: Optional refund reason. Must be one of "duplicate",
                "fraudulent", or "requested_by_customer".

    Returns:
        The created Stripe Refund object.
    """
    s = get_stripe()
    params: dict[str, Any] = {
        "payment_intent": payment_intent_id,
    }
    if amount_cents is not None:
        params["amount"] = amount_cents
    if reason is not None:
        params["reason"] = reason

    return s.Refund.create(**params)


def verify_webhook_signature(
    payload: str | bytes,
    sig_header: str,
    webhook_secret: str,
) -> stripe.Event:
    """
    Verify a Stripe webhook signature and return the parsed event.

    Args:
        payload: The raw request body (string or bytes).
        sig_header: The value of the Stripe-Signature header.
        webhook_secret: The webhook endpoint signing secret (whsec_...).

    Returns:
        The verified Stripe Event object.

    Raises:
        stripe.error.SignatureVerificationError: If the signature
            does not match, indicating the payload may have been
            tampered with.
    """
    s = get_stripe()
    return s.Webhook.construct_event(payload, sig_header, webhook_secret)


def cancel_payment_intent(payment_intent_id: str) -> stripe.PaymentIntent:
    """Cancel an uncaptured PaymentIntent."""
    s = get_stripe()
    return s.PaymentIntent.cancel(payment_intent_id)

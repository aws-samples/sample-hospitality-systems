"""
Lambda handler for POST /payments/intents.

Creates a Stripe PaymentIntent with manual capture for the hotel
pre-authorization flow. Records the authorization in the database
and returns the client_secret for client-side confirmation.
"""

from utils.logger import get_logger
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from utils.database import get_conn
from utils.response import created, bad_request, not_found, server_error
from utils.auth import get_claims
from utils.validation import parse_body, require_fields, validate_uuid
from utils.stripe_client import create_payment_intent, create_customer

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


def handler(event, context):
    """Create a payment intent for a reservation."""
    try:
        # Auth required
        try:
            claims = get_claims(event)
            cognito_sub = claims["sub"]
        except (KeyError, TypeError):
            return server_error("Authentication context missing.")

        # Parse and validate body
        body = parse_body(event)
        field_error = require_fields(body, ["amount", "guestId"])
        if field_error:
            return field_error

        amount = body["amount"]
        currency = body.get("currency", "USD").upper()
        reservation_id = body.get("reservationId") or None
        guest_id = body["guestId"]

        # Validate amount
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return bad_request("Amount must be a valid number.")

        if amount <= 0:
            return bad_request("Amount must be greater than zero.")

        # Validate UUIDs
        if reservation_id and not validate_uuid(reservation_id):
            return bad_request("Invalid reservationId format.")
        if not validate_uuid(guest_id):
            return bad_request("Invalid guestId format.")

        # Look up guest's stripe_customer_id
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT guest_id, cognito_sub, stripe_customer_id, email, first_name, last_name FROM guests WHERE guest_id = %s",
                    (guest_id,),
                )
                guest = cur.fetchone()

            if not guest:
                conn.commit()
                return not_found("Guest not found.")

            if guest["cognito_sub"] != cognito_sub:
                conn.commit()
                return bad_request("Guest ID does not match authenticated user.")

            stripe_customer_id = guest.get("stripe_customer_id")
            if not stripe_customer_id:
                # Auto-create a Stripe customer for this guest
                email = guest.get("email", "")
                name = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
                stripe_cust = create_customer(
                    email=email or "guest@anycompanyhotels.com",
                    name=name or "Guest",
                    metadata={"guest_id": guest_id},
                )
                stripe_customer_id = stripe_cust.id
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE guests SET stripe_customer_id = %s WHERE guest_id = %s",
                        (stripe_customer_id, guest_id),
                    )

            # Convert dollars to cents for Stripe
            amount_cents = int(round(amount * 100))

            # Create Stripe PaymentIntent
            payment_intent = create_payment_intent(
                amount_cents=amount_cents,
                currency=currency.lower(),
                customer_id=stripe_customer_id,
                metadata={
                    "reservation_id": reservation_id,
                    "guest_id": guest_id,
                },
            )

            # Insert authorization record only if we have a reservation
            auth_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            if reservation_id:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO payment_authorizations (
                            authorization_id, guest_id, reservation_id,
                            stripe_payment_intent_id, amount, currency,
                            status, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            auth_id, guest_id, reservation_id,
                            payment_intent.id, amount, currency,
                            "AUTHORIZED", now, now,
                        ),
                    )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return created({
            "authorization_id": auth_id,
            "client_secret": payment_intent.client_secret,
            "stripe_payment_intent_id": payment_intent.id,
            "amount": str(amount),
            "amount_cents": amount_cents,
            "currency": currency,
            "status": "REQUIRES_CONFIRMATION",
        })

    except Exception as e:
        logger.exception("Error creating payment intent")
        return server_error("Failed to create payment intent.")

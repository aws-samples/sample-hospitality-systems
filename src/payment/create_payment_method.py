"""
Lambda handler for POST /payment-methods.

Attaches a Stripe PaymentMethod (created client-side via Stripe.js)
to the guest's Stripe customer and stores a reference in the database.
Raw card data is never handled -- only the Stripe-tokenized payment
method ID.
"""

from utils.logger import get_logger
import os
import uuid
from datetime import datetime, timezone

from utils.database import get_conn
from utils.response import created, bad_request, not_found, server_error
from utils.auth import get_claims
from utils.validation import parse_body, require_fields
from utils.stripe_client import get_stripe

logger = get_logger("payment")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


def handler(event, context):
    """Attach and store a payment method for the authenticated guest."""
    try:
        # Auth required
        claims = get_claims(event)
        cognito_sub = claims["sub"]

        # Parse and validate body
        body = parse_body(event)
        field_error = require_fields(body, ["stripePaymentMethodId"])
        if field_error:
            return field_error

        stripe_pm_id = body["stripePaymentMethodId"]

        # Look up guest by cognito_sub
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT guest_id, stripe_customer_id FROM guests WHERE cognito_sub = %s",
                    (cognito_sub,),
                )
                guest = cur.fetchone()

            if not guest:
                conn.commit()
                return not_found("Guest profile not found. Please create a profile first.")

            stripe_customer_id = guest["stripe_customer_id"]
            guest_id = str(guest["guest_id"])

            if not stripe_customer_id:
                conn.commit()
                return bad_request("Guest does not have a Stripe customer on file.")

            # Attach payment method to Stripe customer
            s = get_stripe()
            s.PaymentMethod.attach(stripe_pm_id, customer=stripe_customer_id)

            # Retrieve payment method details from Stripe
            pm_details = s.PaymentMethod.retrieve(stripe_pm_id)

            card = pm_details.get("card", {})
            last4 = card.get("last4", "")
            brand = card.get("brand", "")
            exp_month = card.get("exp_month")
            exp_year = card.get("exp_year")

            # Insert stored payment method record
            pm_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stored_payment_methods (
                        payment_method_id, guest_id, stripe_payment_method_id,
                        stripe_customer_id, brand, last4,
                        exp_month, exp_year, is_default,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        pm_id, guest_id, stripe_pm_id,
                        stripe_customer_id, brand, last4,
                        exp_month, exp_year, False,
                        now, now,
                    ),
                )
                stored_pm = cur.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return created({
            "payment_method_id": pm_id,
            "stripe_payment_method_id": stripe_pm_id,
            "brand": brand,
            "last4": last4,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "is_default": False,
            "created_at": now.isoformat(),
        })

    except KeyError:
        logger.exception("Missing auth claims")
        return server_error("Authentication context missing.")
    except Exception as e:
        logger.exception("Error creating payment method")
        return server_error("Failed to create payment method.")

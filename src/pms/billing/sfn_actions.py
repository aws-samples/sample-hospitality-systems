"""
PMS Billing Step Functions Actions.

Lambda invoked by CheckoutBilling Step Functions workflow.
Handles: calculate_totals, process_payment, record_payment, update_folio_paid, mark_payment_failed
"""

import os
import uuid

from utils.database import get_conn
from utils.logger import get_logger

logger = get_logger("pms-billing-sfn")

TAX_RATE = float(os.environ.get("TAX_RATE", "0.15"))


@logger.inject_lambda_context
def handler(event, context):
    """Route to appropriate action."""
    action = event.get("action")
    logger.info("Billing SFN action", action=action)

    actions = {
        "calculate_totals": _calculate_totals,
        "process_payment": _process_payment,
        "record_payment": _record_payment,
        "update_folio_paid": _update_folio_paid,
        "mark_payment_failed": _mark_payment_failed,
    }

    if action not in actions:
        raise ValueError(f"Unknown billing action: {action}")

    return actions[action](event)


def _calculate_totals(event):
    """Calculate folio totals and add tax charge."""
    reservation_id = event["reservationId"]

    with get_conn() as conn, conn.cursor() as cur:
        # Find folio
        cur.execute(
            "SELECT folio_id, status FROM folios WHERE reservation_id = %s",
            [reservation_id],
        )
        folio = cur.fetchone()
        if not folio:
            raise ValueError(f"No folio found for reservation {reservation_id}")

        folio_id = folio["folio_id"]

        # Sum active charges (excluding TAX)
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) as subtotal FROM charges "
            "WHERE folio_id = %s AND status = 'ACTIVE' AND charge_type != 'TAX'",
            [folio_id],
        )
        subtotal = float(cur.fetchone()["subtotal"])

        # Idempotent tax creation
        cur.execute(
            "SELECT charge_id FROM charges "
            "WHERE folio_id = %s AND charge_type = 'TAX' AND status = 'ACTIVE'",
            [folio_id],
        )
        existing_tax = cur.fetchone()

        if not existing_tax:
            tax_amount = round(subtotal * TAX_RATE, 2)
            tax_charge_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO charges "
                "(charge_id, folio_id, charge_type, description, amount, charge_date) "
                "VALUES (%s, %s, 'TAX', %s, %s, CURRENT_DATE)",
                [tax_charge_id, folio_id, f"Tax ({int(TAX_RATE * 100)}%)", tax_amount],
            )
        else:
            cur.execute(
                "SELECT amount FROM charges WHERE charge_id = %s",
                [existing_tax["charge_id"]],
            )
            tax_amount = float(cur.fetchone()["amount"])

        total_amount = round(subtotal + tax_amount, 2)

        # Update folio
        cur.execute(
            "UPDATE folios SET subtotal = %s, tax_amount = %s, total_amount = %s, "
            "status = 'PENDING_PAYMENT', updated_at = now() WHERE folio_id = %s",
            [subtotal, tax_amount, total_amount, folio_id],
        )
        conn.commit()

    logger.info("Calculated totals", folio_id=str(folio_id),
               subtotal=subtotal, tax=tax_amount, total=total_amount)

    return {
        "folioId": str(folio_id),
        "subtotal": subtotal,
        "taxAmount": tax_amount,
        "totalAmount": total_amount,
        "reservationId": reservation_id,
    }


def _process_payment(event):
    """Process payment via Stripe (simulated for now — calls CRS payment service)."""
    total_amount = event.get("totalAmount", 0)
    reservation_id = event.get("reservationId")

    # In production, this would call the CRS PaymentService to capture
    # the Stripe PaymentIntent. For now, simulate success.
    logger.info("Processing payment", amount=total_amount, reservation_id=reservation_id)

    # Simulate payment success
    # TODO: Replace with actual CRS PaymentService call:
    # response = invoke_payment_capture(reservation_id, total_amount)
    payment_intent_id = f"pi_simulated_{uuid.uuid4().hex[:16]}"

    return {
        "paymentIntentId": payment_intent_id,
        "amount": total_amount,
        "status": "captured",
        "reservationId": reservation_id,
        "folioId": event.get("folioId"),
    }


def _record_payment(event):
    """Record the payment in the payments table."""
    folio_id = event["folioId"]
    amount = event["amount"]
    payment_intent_id = event.get("paymentIntentId", "")
    reservation_id = event.get("reservationId")

    with get_conn() as conn, conn.cursor() as cur:
        # Get guest_id from folio
        cur.execute("SELECT guest_id FROM folios WHERE folio_id = %s", [folio_id])
        folio = cur.fetchone()

        payment_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO payments "
            "(payment_id, folio_id, reservation_id, guest_id, amount, "
            "method, stripe_payment_intent_id, status) "
            "VALUES (%s, %s, %s, %s, %s, 'STRIPE', %s, 'APPROVED')",
            [payment_id, folio_id, reservation_id,
             folio["guest_id"] if folio else None, amount, payment_intent_id],
        )
        conn.commit()

    logger.info("Payment recorded", payment_id=payment_id, amount=amount)
    return {"paymentId": payment_id, **event}


def _update_folio_paid(event):
    """Mark folio as PAID."""
    folio_id = event["folioId"]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE folios SET status = 'PAID', paid_at = now(), "
            "payment_method = 'STRIPE', updated_at = now() WHERE folio_id = %s",
            [folio_id],
        )
        conn.commit()

    logger.info("Folio marked as PAID", folio_id=folio_id)
    return event


def _mark_payment_failed(event):
    """Mark folio as PAYMENT_FAILED."""
    folio_id = event.get("folioId")
    if not folio_id:
        # Try to find folio from reservation
        reservation_id = event.get("reservationId")
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT folio_id FROM folios WHERE reservation_id = %s",
                [reservation_id],
            )
            row = cur.fetchone()
            folio_id = str(row["folio_id"]) if row else None

    if folio_id:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE folios SET status = 'PAYMENT_FAILED', updated_at = now() "
                "WHERE folio_id = %s",
                [folio_id],
            )
            conn.commit()

    logger.error("Payment failed", folio_id=folio_id, error=event.get("error"))
    return {"folioId": folio_id, "status": "PAYMENT_FAILED"}

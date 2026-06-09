"""
PMS Notifications Service.

SQS consumer that sends email notifications via SES based on system events.
Handles: reservation.confirmed, checkinout.checked_in, billing.payment_processed, loyalty.tier_changed
"""

import json
import os
from utils.logger import get_logger

logger = get_logger("pms-notifications")

SES_CLIENT = None
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "noreply@anycompanyhotels.com")
ENABLED = os.environ.get("NOTIFICATIONS_ENABLED", "true").lower() == "true"


def _pick(detail, *keys):
    """Return the first non-empty value from detail for any of the given keys."""
    for key in keys:
        value = detail.get(key)
        if value is not None and value != "":
            return value
    return None


def get_ses_client():
    global SES_CLIENT
    if SES_CLIENT is None:
        import boto3
        SES_CLIENT = boto3.client("ses")
    return SES_CLIENT


@logger.inject_lambda_context
def handler(event, context):
    """Process SQS batch of notification events."""
    failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            detail_type = body.get("detail-type", "")
            detail = body.get("detail", {})

            if detail_type in ("reservation.confirmed", "reservation.created"):
                _send_reservation_confirmation(detail)
            elif detail_type == "billing.payment_processed":
                _send_checkout_receipt(detail)
            elif detail_type == "loyalty.tier_changed":
                _send_tier_upgrade(detail)
            elif detail_type == "checkinout.checked_in":
                _send_checkin_confirmation(detail)
            else:
                logger.info("No notification template for event", detail_type=detail_type)

        except Exception as e:
            logger.exception("Failed to process notification",
                           message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}


def _send_reservation_confirmation(detail):
    """Send booking confirmation email."""
    guest_id = _pick(detail, "guestId", "guest_id")
    reservation_id = _pick(detail, "reservationId", "reservation_id")
    confirmation_number = _pick(detail, "confirmationNumber", "confirmation_number") or (
        reservation_id[:8] if reservation_id else ""
    )

    # Get guest email from DB
    email = _get_guest_email(guest_id)
    if not email:
        logger.warning("No email for guest, skipping notification", guest_id=guest_id)
        return

    subject = f"Booking Confirmed - {confirmation_number}"
    body_html = f"""
    <h2>Your Reservation is Confirmed!</h2>
    <p>Confirmation Number: <strong>{confirmation_number}</strong></p>
    <p>Check-in: {_pick(detail, 'checkInDate', 'check_in_date') or 'N/A'}</p>
    <p>Check-out: {_pick(detail, 'checkOutDate', 'check_out_date') or 'N/A'}</p>
    <p>Room Type: {_pick(detail, 'roomType', 'room_type') or 'N/A'}</p>
    <p>Thank you for choosing AnyCompany Hotels & Resorts.</p>
    """

    _send_email(email, subject, body_html)
    logger.info("Sent reservation confirmation", guest_id=guest_id, reservation_id=reservation_id)


def _send_checkout_receipt(detail):
    """Send checkout receipt email."""
    guest_id = _pick(detail, "guestId", "guest_id")
    amount = float(_pick(detail, "amount", "totalAmount", "total_amount") or 0)
    reservation_id = _pick(detail, "reservationId", "reservation_id")

    email = _get_guest_email(guest_id)
    if not email:
        return

    subject = "Your Checkout Receipt - AnyCompany Hotel"
    body_html = f"""
    <h2>Thank You for Your Stay!</h2>
    <p>Your checkout is complete.</p>
    <p>Total Charged: <strong>${amount:.2f}</strong></p>
    <p>Payment Method: Credit Card on file</p>
    <p>We hope you enjoyed your stay. See you again soon!</p>
    """

    _send_email(email, subject, body_html)
    logger.info("Sent checkout receipt", guest_id=guest_id, amount=amount)


def _send_tier_upgrade(detail):
    """Send loyalty tier upgrade email."""
    guest_id = _pick(detail, "guestId", "guest_id")
    new_tier = _pick(detail, "newTier", "new_tier")
    previous_tier = _pick(detail, "previousTier", "previous_tier")

    email = _get_guest_email(guest_id)
    if not email:
        return

    tier_benefits = {
        "SILVER": "1.25x points multiplier on all stays",
        "GOLD": "1.5x points multiplier on all stays",
        "DIAMOND": "2x points multiplier on all stays, priority room upgrades",
    }

    subject = f"Congratulations! You've reached {new_tier} status"
    body_html = f"""
    <h2>🎉 Tier Upgrade!</h2>
    <p>You've been upgraded from <strong>{previous_tier}</strong> to <strong>{new_tier}</strong>!</p>
    <p>Your new benefits: {tier_benefits.get(new_tier, '')}</p>
    <p>Thank you for your loyalty to AnyCompany Hotels & Resorts.</p>
    """

    _send_email(email, subject, body_html)
    logger.info("Sent tier upgrade notification", guest_id=guest_id, new_tier=new_tier)


def _send_checkin_confirmation(detail):
    """Send check-in confirmation email."""
    guest_id = _pick(detail, "guestId", "guest_id")
    room_number = _pick(detail, "roomNumber", "room_number") or ""

    email = _get_guest_email(guest_id)
    if not email:
        return

    subject = "Welcome! You're Checked In - AnyCompany Hotel"
    body_html = f"""
    <h2>Welcome to AnyCompany Hotel!</h2>
    <p>You're all set. Your room: <strong>{room_number}</strong></p>
    <p>If you need anything during your stay, don't hesitate to contact the front desk.</p>
    <p>Enjoy your stay!</p>
    """

    _send_email(email, subject, body_html)
    logger.info("Sent check-in confirmation", guest_id=guest_id, room=room_number)


def _get_guest_email(guest_id):
    """Fetch guest email from database."""
    if not guest_id:
        return None

    from utils.database import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM guests WHERE guest_id = %s", [guest_id])
            row = cur.fetchone()
            return row["email"] if row else None


def _send_email(to_email, subject, body_html):
    """Send email via SES (or log if disabled)."""
    if not ENABLED:
        logger.info("Notifications disabled, logging only",
                   to=to_email, subject=subject)
        return

    try:
        get_ses_client().send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
        )
    except Exception as e:
        logger.exception("Failed to send email via SES", to=to_email, subject=subject)
        # Don't re-raise — notification failure shouldn't block the workflow

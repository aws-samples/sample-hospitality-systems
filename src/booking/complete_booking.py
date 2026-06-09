"""
Lambda handler for POST /booking/cart/{cartId}/book.

Completes the booking process by converting a cart into a confirmed reservation.
Orchestrates guest profile lookup/creation, Stripe payment authorization and
capture, reservation creation, availability updates, and payment record keeping
within a single database transaction.

Authentication required — guest must be logged in.
"""

import json
from utils.logger import get_logger
import os
import secrets
import string
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from utils.database import get_conn
from utils.response import ok, error, created, bad_request, not_found, server_error, forbidden, transform_keys
from utils.auth import get_claims, get_guest_id, has_group
from utils.events import publish_event
from utils.validation import parse_body, require_fields, validate_uuid
from utils.stripe_client import capture_payment, cancel_payment_intent

logger = get_logger("booking")

stripe_secret_arn = os.environ.get("STRIPE_SECRET_ARN")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def _generate_confirmation_number():
    """Generate a unique confirmation number in format RES-XXXXXX."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"RES-{random_part}"


def handler(event, context):
    """Complete a booking from a cart — create reservation and process payment."""
    try:
        # Auth required
        try:
            claims = get_claims(event)
            cognito_sub = claims["sub"]
        except (KeyError, TypeError):
            return error(401, "UNAUTHORIZED", "Authentication required to complete a booking.")

        # Extract cartId from path
        path_params = event.get("pathParameters") or {}
        cart_id = path_params.get("cartId")
        if not cart_id:
            return bad_request("Missing required path parameter: cartId")
        if not validate_uuid(cart_id):
            return bad_request("Invalid cartId format. Expected UUID.")

        body = parse_body(event)
        field_error = require_fields(body, ["guestId", "paymentMethodId"])
        if field_error:
            return field_error

        # paymentMethodId is actually the Stripe PaymentIntent ID from client-side confirmation
        stripe_pi_id = body["paymentMethodId"]
        special_requests = body.get("specialRequests")

        # Admin/Manager callers can operate as a different guest by passing body.guestId.
        is_staff_caller = has_group(event, "Admin", "Manager")
        operate_as_guest_id = body.get("guestId") if is_staff_caller else None
        if operate_as_guest_id and not validate_uuid(operate_as_guest_id):
            return bad_request("Invalid guestId format. Expected UUID.")

        # Skip Stripe API calls when an Admin/Manager submits a synthetic PaymentIntent.
        is_simulator_payment = is_staff_caller and stripe_pi_id.startswith("pi_simulated_")

        # Guest info comes from the guests array
        guests = body.get("guests") or []
        if not guests:
            return bad_request("At least one guest is required.")

        primary_guest = guests[0]
        first_name = primary_guest.get("firstName", "")
        last_name = primary_guest.get("lastName", "")
        email = primary_guest.get("email", "")
        phone = primary_guest.get("phone")

        conn = get_conn()
        payment_intent = None

        try:
            # Fetch the cart
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM booking_carts WHERE cart_id = %s",
                    (cart_id,),
                )
                cart = cur.fetchone()

            if not cart:
                conn.commit()
                return not_found("Booking cart not found.")

            if cart["status"] != "ACTIVE":
                conn.commit()
                return bad_request(f"Cart is no longer active. Current status: {cart['status']}")

            now = datetime.now(timezone.utc)
            if cart["expires_at"] < now:
                conn.commit()
                return bad_request("Cart has expired. Please create a new cart.")

            # Owner-only access: a non-staff caller may only complete their own
            # cart. Staff (Admin/Manager) may complete any cart — they operate on
            # behalf of guests. Anonymous carts (guest_id NULL) have no owner to
            # enforce against and are completed by whoever holds the cartId.
            if not is_staff_caller and cart["guest_id"] is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT guest_id FROM guests WHERE cognito_sub = %s",
                        (cognito_sub,),
                    )
                    caller_guest = cur.fetchone()
                caller_guest_id = str(caller_guest["guest_id"]) if caller_guest else None
                if caller_guest_id != str(cart["guest_id"]):
                    conn.commit()
                    return forbidden("You do not have permission to complete this cart.")

            property_id = str(cart["property_id"])
            room_type_id = str(cart["room_type_id"])
            rate_plan_id = str(cart["rate_plan_id"])
            check_in = cart["check_in_date"]
            check_out = cart["check_out_date"]

            if isinstance(check_in, str):
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
            else:
                check_in_date = check_in

            if isinstance(check_out, str):
                check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
            else:
                check_out_date = check_out

            num_nights = (check_out_date - check_in_date).days
            total_after_tax = Decimal(str(cart["total_after_tax"]))
            total_before_tax = Decimal(str(cart["total_before_tax"]))
            amount_per_night = Decimal(str(cart["amount_per_night"])) if cart["amount_per_night"] else Decimal("0")
            discount_amount = Decimal(str(cart["discount_amount"])) if cart["discount_amount"] else Decimal("0")
            promo_code = cart["promo_code"]
            adults = cart["adults"]
            children = cart["children"]

            # Re-validate availability (someone else may have booked)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS available_nights
                    FROM generate_series(%s::date, %s::date - INTERVAL '1 day', '1 day') AS d(dt)
                    LEFT JOIN availability a
                        ON a.room_type_id = %s AND a.date = d.dt::date
                    WHERE COALESCE(a.available, 0) + COALESCE(a.overbooking_allowance, 0) > 0
                    """,
                    (check_in_date.isoformat(), check_out_date.isoformat(), room_type_id),
                )
                avail = cur.fetchone()

            if avail["available_nights"] < num_nights:
                conn.commit()
                return bad_request(
                    "Room type is no longer available for the requested dates. "
                    "Another guest may have booked this room."
                )

            # Step A: Create or get guest profile
            with conn.cursor() as cur:
                if operate_as_guest_id:
                    cur.execute(
                        "SELECT * FROM guests WHERE guest_id = %s",
                        (operate_as_guest_id,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM guests WHERE cognito_sub = %s",
                        (cognito_sub,),
                    )
                guest = cur.fetchone()

            if operate_as_guest_id and not guest:
                conn.commit()
                return not_found(f"Guest {operate_as_guest_id} not found.")

            if guest:
                guest_id = str(guest["guest_id"])
                stripe_customer_id = guest["stripe_customer_id"]

                # Update guest info if needed (skip in operate-as mode — caller is not the guest)
                if not operate_as_guest_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE guests SET
                                first_name = COALESCE(%s, first_name),
                                last_name = COALESCE(%s, last_name),
                                phone = COALESCE(%s, phone),
                                updated_at = %s
                            WHERE guest_id = %s
                            """,
                            (first_name, last_name, phone, now, guest_id),
                        )
            else:
                # Create new guest with Stripe customer
                from utils.stripe_client import create_customer

                full_name = f"{first_name} {last_name}"
                stripe_customer = create_customer(
                    email=email,
                    name=full_name,
                    metadata={"cognito_sub": cognito_sub},
                )
                stripe_customer_id = stripe_customer.id
                guest_id = str(uuid.uuid4())

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO guests (
                            guest_id, cognito_sub, stripe_customer_id,
                            first_name, last_name, email, phone,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            guest_id, cognito_sub, stripe_customer_id,
                            first_name, last_name, email, phone,
                            now, now,
                        ),
                    )

            # Step B: Use the already-confirmed PaymentIntent from client-side Stripe Elements
            amount_cents = int((total_after_tax * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            reservation_id = str(uuid.uuid4())
            confirmation_number = _generate_confirmation_number()

            # The PaymentIntent was already created and confirmed client-side
            # We just need to reference it for capture later
            if is_simulator_payment:
                payment_intent = SimpleNamespace(
                    id=stripe_pi_id, latest_charge=None, charges=None, client_secret=None,
                )
            else:
                from utils.stripe_client import get_stripe
                s = get_stripe()
                payment_intent = s.PaymentIntent.retrieve(stripe_pi_id)

            # Step C: Get rate plan and room type snapshot data
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rp.code, rp.name, rp.description, rp.cancellation_policy
                    FROM rate_plans rp WHERE rp.rate_plan_id = %s
                    """,
                    (rate_plan_id,),
                )
                rate_plan_snap = cur.fetchone()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rt.code, rt.name
                    FROM room_types rt WHERE rt.room_type_id = %s
                    """,
                    (room_type_id,),
                )
                room_type_snap = cur.fetchone()

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code AS hotel_code FROM properties WHERE property_id = %s",
                    (property_id,),
                )
                property_snap = cur.fetchone()

            # Determine refundable based on cancellation policy
            cancellation_policy = rate_plan_snap["cancellation_policy"] if rate_plan_snap else "FLEXIBLE"
            refundable = cancellation_policy != "NON_REFUNDABLE"

            # Determine if same-day booking
            same_day = check_in_date == date.today()

            # Step E: Insert reservation
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reservations (
                        reservation_id, confirmation_number, guest_id, property_id,
                        room_type_id, rate_plan_id, status, adults, children,
                        number_of_nights, number_of_guests, same_day_booking,
                        booked_rate_plan_code, booked_rate_plan_name, booked_rate_plan_description,
                        amount_per_night, total_before_tax, total_after_tax,
                        deposit_amount, refundable, guarantee_type,
                        currency_code, currency_name, currency_symbol,
                        booked_room_type_code, booked_room_type_name,
                        check_in_date, check_out_date,
                        channel_method, hotel_code, brand_code,
                        additional_notes, trip_type,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        reservation_id, confirmation_number, guest_id, property_id,
                        room_type_id, rate_plan_id, "CONFIRMED", adults, children,
                        num_nights, adults + children, same_day,
                        rate_plan_snap["code"] if rate_plan_snap else None,
                        rate_plan_snap["name"] if rate_plan_snap else None,
                        rate_plan_snap["description"] if rate_plan_snap else None,
                        amount_per_night, total_before_tax, total_after_tax,
                        total_after_tax, refundable, "CREDIT_CARD",
                        "USD", "US Dollar", "$",
                        room_type_snap["code"] if room_type_snap else None,
                        room_type_snap["name"] if room_type_snap else None,
                        check_in_date.isoformat(), check_out_date.isoformat(),
                        "WEB", property_snap["hotel_code"] if property_snap else None, "ANY",
                        special_requests, "LEISURE",
                        now, now,
                    ),
                )
                reservation = cur.fetchone()

            # Step F: Update availability (increment sold for each date in range)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE availability
                    SET sold = sold + 1
                    WHERE room_type_id = %s
                      AND date >= %s
                      AND date < %s
                    """,
                    (room_type_id, check_in_date.isoformat(), check_out_date.isoformat()),
                )

            # Step G: Insert payment authorization record
            authorization_id = str(uuid.uuid4())
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payment_authorizations (
                        authorization_id, reservation_id, guest_id,
                        stripe_payment_intent_id, stripe_customer_id,
                        amount, currency, status,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        authorization_id, reservation_id, guest_id,
                        payment_intent.id, stripe_customer_id,
                        total_after_tax, "USD", "AUTHORIZED",
                        now, now,
                    ),
                )

            # Step H: Update cart status to CONVERTED
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE booking_carts SET
                        status = 'CONVERTED',
                        guest_id = %s,
                        updated_at = %s
                    WHERE cart_id = %s
                    """,
                    (guest_id, now, cart_id),
                )

            # Step I: If promo code was used, increment used_count
            if promo_code:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE promo_codes
                        SET used_count = used_count + 1
                        WHERE LOWER(code) = LOWER(%s)
                        """,
                        (promo_code,),
                    )

            conn.commit()

        except Exception:
            conn.rollback()
            # Cancel the uncaptured payment intent if it was created (skip for synthetic IDs)
            if payment_intent and not is_simulator_payment:
                try:
                    cancel_payment_intent(payment_intent.id)
                except Exception:
                    logger.warning("Failed to cancel PaymentIntent", payment_intent_id=payment_intent.id)
            raise

        # Step J: Capture payment AFTER successful DB commit
        if is_simulator_payment:
            captured_intent = payment_intent
        else:
            captured_intent = capture_payment(
                payment_intent_id=payment_intent.id,
                amount_cents=amount_cents,
            )

        # Update authorization status to CAPTURED and insert capture record
        capture_id = str(uuid.uuid4())
        stripe_charge_id = None
        receipt_url = None
        if hasattr(captured_intent, "latest_charge") and captured_intent.latest_charge:
            stripe_charge_id = captured_intent.latest_charge
        if hasattr(captured_intent, "charges") and captured_intent.charges and captured_intent.charges.data:
            charge = captured_intent.charges.data[0]
            stripe_charge_id = charge.id
            receipt_url = getattr(charge, "receipt_url", None)

        try:
            conn2 = get_conn()
            with conn2.cursor() as cur:
                cur.execute(
                    "UPDATE payment_authorizations SET status = 'CAPTURED', updated_at = %s WHERE authorization_id = %s",
                    (datetime.now(timezone.utc), authorization_id),
                )
                cur.execute(
                    """
                    INSERT INTO payment_captures (
                        capture_id, authorization_id, captured_amount,
                        stripe_charge_id, receipt_url, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (capture_id, authorization_id, total_after_tax, stripe_charge_id, receipt_url, datetime.now(timezone.utc)),
                )
            conn2.commit()
        except Exception as cap_err:
            logger.warning("Failed to record capture in DB", error=str(cap_err))

        # Publish events (outside transaction — best effort)
        try:
            publish_event(
                source="anycompany.reservations",
                detail_type="reservation.created",
                detail={
                    "reservationId": reservation_id,
                    "confirmationNumber": confirmation_number,
                    "guestId": guest_id,
                    "propertyId": property_id,
                    "roomTypeId": room_type_id,
                    "ratePlanId": rate_plan_id,
                    "checkInDate": check_in_date.isoformat(),
                    "checkOutDate": check_out_date.isoformat(),
                    "numberOfNights": num_nights,
                    "adults": adults,
                    "children": children,
                    "totalAfterTax": str(total_after_tax),
                    "currency": "USD",
                    "status": "CONFIRMED",
                    "channelMethod": "WEB",
                },
            )

            publish_event(
                source="anycompany.payments",
                detail_type="payment.captured",
                detail={
                    "reservationId": reservation_id,
                    "confirmationNumber": confirmation_number,
                    "guestId": guest_id,
                    "authorizationId": authorization_id,
                    "captureId": capture_id,
                    "stripePaymentIntentId": payment_intent.id,
                    "stripeCustomerId": stripe_customer_id,
                    "amount": str(total_after_tax),
                    "currency": "USD",
                },
            )
        except Exception as event_err:
            logger.warning("Failed to publish events", error=str(event_err))

        # Build response
        serialized_reservation = _serialize_row(reservation)

        response_data = {
            "reservation": serialized_reservation,
            "confirmation_number": confirmation_number,
            "payment_summary": {
                "stripe_payment_intent_id": payment_intent.id,
                "amount": str(total_after_tax),
                "currency": "USD",
                "status": "CAPTURED",
                "total_before_tax": str(total_before_tax),
                "discount_amount": str(discount_amount),
                "tax_amount": str(total_after_tax - (total_before_tax - discount_amount)),
                "total_after_tax": str(total_after_tax),
            },
            "guest": {
                "guest_id": guest_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
            },
        }

        return created(response_data)

    except Exception as e:
        logger.exception("Error completing booking")
        return server_error("Failed to complete booking.")

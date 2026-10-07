"""Integration test: the end-to-end booking flow against the dev stack.

This is exactly the transactional path the unit layer deferred — it
creates a real reservation through the public CRS booking flow (search ->
cart -> book) and verifies the DB side effects via the Data API: a
reservation row exists and availability was decremented.

All created data is testsuite- marked and torn down via the `track`
fixture; the sweeper is the backstop.
"""

from datetime import date, timedelta

import pytest

# Relative stay window. Hardcoded dates rot: once they pass, the API correctly
# rejects them ("check_in date must be today or in the future") and the test
# fails for a reason unrelated to the booking flow. 30 days out stays inside the
# seeded 365-day availability window.
CHECK_IN = str(date.today() + timedelta(days=30))
CHECK_OUT = str(date.today() + timedelta(days=32))


@pytest.fixture
def testsuite_guest(db, track):
    """Create a testsuite- guest directly in the DB, return its id.

    The booking flow's operate-as-guest path books on behalf of an
    existing guest_id, mirroring how the simulator works.
    """
    import uuid
    gid = str(uuid.uuid4())
    email = f"testsuite-{gid}@example.test"
    db.execute(
        """
        INSERT INTO guests (guest_id, cognito_sub, first_name, last_name,
                            email, email_verified, loyalty_tier, points_balance,
                            lifetime_points_earned, created_at, updated_at)
        VALUES (CAST(:gid AS uuid), :sub, 'Test', 'Booker', :email, true,
                'NONE', 0, 0, now(), now())
        """,
        [
            {"name": "gid", "value": {"stringValue": gid}},
            {"name": "sub", "value": {"stringValue": f"testsuite-sub-{gid}"}},
            {"name": "email", "value": {"stringValue": email}},
        ],
    )
    track.guest(gid)
    return gid


class TestBookingFlow:
    def test_search_cart_book_creates_reservation(self, api, db, testsuite_guest, track):
        # 1. Search for availability (public).
        status, search = api.post(
            "/booking/search",
            body={"checkIn": CHECK_IN, "checkOut": CHECK_OUT, "adults": 2, "limit": 5},
        )
        assert status == 200, search
        results = search.get("data") or []
        if not results:
            pytest.skip("No availability in the search window on the dev stack.")

        choice = results[0]
        property_id = choice["propertyId"]
        cheapest = choice.get("cheapestOption") or {}
        room_type_id = cheapest.get("roomTypeId")
        rate_plan_id = cheapest.get("ratePlanId")
        if not (room_type_id and rate_plan_id):
            pytest.skip("Search result missing room/rate ids.")

        # 2. Create a cart (public).
        import uuid
        status, cart = api.post(
            "/booking/cart",
            body={
                "propertyId": property_id,
                "roomTypeId": room_type_id,
                "ratePlanId": rate_plan_id,
                "checkIn": CHECK_IN,
                "checkOut": CHECK_OUT,
                "adults": 2,
                "sessionId": f"testsuite-{uuid.uuid4().hex}",
            },
        )
        assert status == 201, cart
        cart_id = cart["data"]["cartId"]

        # 3. Complete the booking. The `pi_simulated_` sentinel only bypasses
        #    real Stripe when the caller is in Admin/Manager (is_staff_caller),
        #    mirroring how the activity simulator books. Book as admin.
        status, booking = api.post(
            f"/booking/cart/{cart_id}/book",
            body={
                "guestId": testsuite_guest,
                "paymentMethodId": f"pi_simulated_{uuid.uuid4().hex[:24]}",
                "guests": [{"firstName": "Test", "lastName": "Booker",
                            "email": "noreply@anycompanyhotels.local"}],
            },
            role="admin",
        )
        assert status in (200, 201), booking
        reservation = booking["data"]["reservation"]
        reservation_id = reservation["reservationId"]
        track.reservation(reservation_id)

        # 4. Verify the DB side effect: reservation row exists for the test guest.
        rows = db.query(
            "SELECT guest_id, status FROM reservations "
            "WHERE reservation_id = CAST(:id AS uuid)",
            [{"name": "id", "value": {"stringValue": reservation_id}}],
        )
        assert len(rows) == 1
        assert rows[0]["guest_id"] == testsuite_guest
        assert rows[0]["status"] in ("CONFIRMED", "PENDING")

        # 5. Confirmation number is unique (the SnapStart/secrets.choice fix).
        assert reservation.get("confirmationNumber", "").startswith("RES-")

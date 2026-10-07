"""Unit tests for the booking domain handlers.

Public booking flow (search, rates, cart CRUD, promo) plus the
authenticated complete_booking. Validation gates and not-found/expired
branches are covered deterministically; deep pricing + Stripe-capture
flows are deferred to the integration layer.
"""

import json
from datetime import UTC, date, timedelta

import pytest

PROP = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
ROOM = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"
RATE = "b2c3d4e5-f6a7-4890-bcde-f01234567890"
CART = "c3d4e5f6-a7b8-4901-cdef-012345678901"


def _body(resp):
    return json.loads(resp["body"])


def _future(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def search(load_handler):
    return load_handler("booking/search.py")


@pytest.fixture
def get_rates(load_handler):
    return load_handler("booking/get_rates.py")


@pytest.fixture
def create_cart(load_handler):
    return load_handler("booking/create_cart.py")


@pytest.fixture
def update_cart(load_handler):
    return load_handler("booking/update_cart.py")


@pytest.fixture
def apply_promo(load_handler):
    return load_handler("booking/apply_promo.py")


@pytest.fixture
def complete_booking(load_handler):
    return load_handler("booking/complete_booking.py")


class TestSearch:
    def test_requires_dates(self, search):
        assert search.handler({"body": "{}"}, None)["statusCode"] == 400

    def test_bad_date_range(self, search):
        resp = search.handler(
            {"body": json.dumps({"checkIn": _future(3), "checkOut": _future(1)})}, None
        )
        assert resp["statusCode"] == 400


class TestGetRates:
    def test_requires_property(self, get_rates):
        assert get_rates.handler({"queryStringParameters": {}}, None)["statusCode"] == 400

    def test_invalid_property_uuid(self, get_rates):
        resp = get_rates.handler(
            {"queryStringParameters": {"propertyId": "x", "roomTypeId": ROOM,
                                        "checkIn": _future(1), "checkOut": _future(3)}},
            None,
        )
        assert resp["statusCode"] == 400

    def test_invalid_room_uuid(self, get_rates):
        resp = get_rates.handler(
            {"queryStringParameters": {"propertyId": PROP, "roomTypeId": "x",
                                        "checkIn": _future(1), "checkOut": _future(3)}},
            None,
        )
        assert resp["statusCode"] == 400


class TestCreateCart:
    def test_requires_fields(self, create_cart):
        assert create_cart.handler({"body": "{}"}, None)["statusCode"] == 400

    def test_invalid_uuid(self, create_cart):
        resp = create_cart.handler(
            {"body": json.dumps({
                "propertyId": "x", "roomTypeId": ROOM, "ratePlanId": RATE,
                "checkIn": _future(1), "checkOut": _future(3), "adults": 2,
                "sessionId": "sess-1234",
            })},
            None,
        )
        assert resp["statusCode"] == 400


class TestUpdateCart:
    def test_missing_cart_id(self, update_cart):
        assert update_cart.handler({"pathParameters": {}}, None)["statusCode"] == 400

    def test_invalid_cart_id(self, update_cart):
        resp = update_cart.handler({"pathParameters": {"cartId": "x"}}, None)
        assert resp["statusCode"] == 400

    def test_body_required(self, update_cart):
        resp = update_cart.handler({"pathParameters": {"cartId": CART}}, None)
        assert resp["statusCode"] == 400

    def test_cart_not_found(self, update_cart, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(update_cart, "get_conn", lambda: mock_db.conn)
        resp = update_cart.handler(
            {"pathParameters": {"cartId": CART}, "body": json.dumps({"adults": 2})}, None
        )
        assert resp["statusCode"] == 404


class TestApplyPromo:
    def test_missing_cart_id(self, apply_promo):
        assert apply_promo.handler({"pathParameters": {}, "body": "{}"}, None)["statusCode"] == 400

    def test_invalid_cart_id(self, apply_promo):
        resp = apply_promo.handler(
            {"pathParameters": {"cartId": "x"}, "body": json.dumps({"promoCode": "X"})}, None
        )
        assert resp["statusCode"] == 400

    def test_requires_promo_code(self, apply_promo):
        resp = apply_promo.handler(
            {"pathParameters": {"cartId": CART}, "body": "{}"}, None
        )
        assert resp["statusCode"] == 400

    def test_cart_not_found(self, apply_promo, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(apply_promo, "get_conn", lambda: mock_db.conn)
        resp = apply_promo.handler(
            {"pathParameters": {"cartId": CART}, "body": json.dumps({"promoCode": "SAVE10"})},
            None,
        )
        assert resp["statusCode"] == 404


class TestCompleteBooking:
    def test_requires_auth(self, complete_booking):
        resp = complete_booking.handler(
            {"requestContext": {}, "pathParameters": {"cartId": CART}, "body": "{}"}, None
        )
        assert resp["statusCode"] == 401

    def test_invalid_cart_id(self, complete_booking, make_event):
        ev = make_event(path_params={"cartId": "x"}, body={}, sub="cog-sub")
        assert complete_booking.handler(ev, None)["statusCode"] == 400

    def test_requires_fields(self, complete_booking, make_event):
        ev = make_event(path_params={"cartId": CART}, body={}, sub="cog-sub")
        assert complete_booking.handler(ev, None)["statusCode"] == 400

    def test_cart_not_found(self, complete_booking, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)  # cart lookup misses
        monkeypatch.setattr(complete_booking, "get_conn", lambda: mock_db.conn)
        ev = make_event(
            path_params={"cartId": CART},
            body={"guestId": ROOM, "paymentMethodId": "pi_123",
                  "guests": [{"firstName": "A", "lastName": "B", "email": "a@b.com"}]},
            sub="cog-sub",
        )
        assert complete_booking.handler(ev, None)["statusCode"] == 404

    def test_other_guests_cart_forbidden(self, complete_booking, make_event, mock_db, monkeypatch):
        # A non-staff caller cannot complete a cart owned by a different guest.
        from datetime import datetime, timezone
        from datetime import timedelta as _td
        active_cart = {
            "cart_id": CART, "guest_id": "owner-guest-id", "status": "ACTIVE",
            "expires_at": datetime.now(UTC) + _td(minutes=20),
        }
        mock_db.queue(fetchone=active_cart)                      # cart lookup → owned by someone else
        mock_db.queue(fetchone={"guest_id": "caller-guest-id"})  # caller's own guest row → different id
        monkeypatch.setattr(complete_booking, "get_conn", lambda: mock_db.conn)
        ev = make_event(
            path_params={"cartId": CART},
            body={"guestId": ROOM, "paymentMethodId": "pi_123",
                  "guests": [{"firstName": "A", "lastName": "B", "email": "a@b.com"}]},
            sub="cog-sub",
        )
        assert complete_booking.handler(ev, None)["statusCode"] == 403

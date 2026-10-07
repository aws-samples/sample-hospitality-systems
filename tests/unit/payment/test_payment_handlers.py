"""Unit tests for the payment domain handlers.

Covers auth/validation gates, ownership/not-found branches, and the
Stripe webhook signature-verification branches. Deep capture/refund
flows are deferred to integration; Stripe SDK calls are mocked.
"""

import json

import pytest

PAYMENT = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
GUEST = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"
SUB = "cog-sub-1"


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture
def get_payment(load_handler):
    return load_handler("payment/get_payment.py")


@pytest.fixture
def list_payment_methods(load_handler):
    return load_handler("payment/list_payment_methods.py")


@pytest.fixture
def create_intent(load_handler):
    return load_handler("payment/create_intent.py")


@pytest.fixture
def confirm_payment(load_handler):
    return load_handler("payment/confirm_payment.py")


@pytest.fixture
def refund_payment(load_handler):
    return load_handler("payment/refund_payment.py")


@pytest.fixture
def create_payment_method(load_handler):
    return load_handler("payment/create_payment_method.py")


@pytest.fixture
def stripe_webhook(load_handler):
    return load_handler("payment/stripe_webhook.py")


class TestGetPayment:
    def test_invalid_id(self, get_payment, make_event):
        ev = make_event(path_params={"paymentId": "x"}, sub=SUB)
        assert get_payment.handler(ev, None)["statusCode"] == 400

    def test_not_found(self, get_payment, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_payment, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"paymentId": PAYMENT}, sub=SUB)
        assert get_payment.handler(ev, None)["statusCode"] == 404


class TestListPaymentMethods:
    def test_guest_not_found(self, list_payment_methods, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(list_payment_methods, "get_conn", lambda: mock_db.conn)
        ev = make_event(sub=SUB)
        assert list_payment_methods.handler(ev, None)["statusCode"] == 404

    def test_lists_methods(self, list_payment_methods, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST})  # guest lookup
        mock_db.queue(fetchall=[                       # stored methods
            {"payment_method_id": "pm1", "guest_id": GUEST, "brand": "visa",
             "last4": "4242", "is_default": True},
        ])
        monkeypatch.setattr(list_payment_methods, "get_conn", lambda: mock_db.conn)
        ev = make_event(sub=SUB)
        resp = list_payment_methods.handler(ev, None)
        assert resp["statusCode"] == 200
        assert _body(resp)["data"][0]["last4"] == "4242"


class TestCreateIntent:
    def test_requires_fields(self, create_intent, make_event):
        ev = make_event(body={}, sub=SUB)
        assert create_intent.handler(ev, None)["statusCode"] == 400

    def test_amount_must_be_positive(self, create_intent, make_event):
        ev = make_event(body={"amount": 0, "guestId": GUEST}, sub=SUB)
        assert create_intent.handler(ev, None)["statusCode"] == 400

    def test_amount_must_be_numeric(self, create_intent, make_event):
        ev = make_event(body={"amount": "lots", "guestId": GUEST}, sub=SUB)
        assert create_intent.handler(ev, None)["statusCode"] == 400

    def test_invalid_guest_uuid(self, create_intent, make_event):
        ev = make_event(body={"amount": 100, "guestId": "x"}, sub=SUB)
        assert create_intent.handler(ev, None)["statusCode"] == 400


class TestConfirmPayment:
    def test_requires_fields(self, confirm_payment, make_event):
        ev = make_event(body={}, sub=SUB)
        assert confirm_payment.handler(ev, None)["statusCode"] == 400

    def test_authorization_not_found(self, confirm_payment, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(confirm_payment, "get_conn", lambda: mock_db.conn)
        ev = make_event(
            body={"paymentIntentId": "pi_1", "authorizationId": GUEST}, sub=SUB
        )
        assert confirm_payment.handler(ev, None)["statusCode"] == 404


class TestRefundPayment:
    def test_invalid_id(self, refund_payment, make_event):
        ev = make_event(path_params={"paymentId": "x"}, body={"reason": "dup"}, sub=SUB)
        assert refund_payment.handler(ev, None)["statusCode"] == 400

    def test_requires_reason(self, refund_payment, make_event):
        ev = make_event(path_params={"paymentId": PAYMENT}, body={}, sub=SUB)
        assert refund_payment.handler(ev, None)["statusCode"] == 400

    def test_invalid_reason(self, refund_payment, make_event):
        # Reason must satisfy the payment_refunds.reason CHECK constraint.
        ev = make_event(
            path_params={"paymentId": PAYMENT}, body={"reason": "requested_by_customer"}, sub=SUB
        )
        assert refund_payment.handler(ev, None)["statusCode"] == 400

    def test_not_found(self, refund_payment, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(refund_payment, "get_conn", lambda: mock_db.conn)
        ev = make_event(
            path_params={"paymentId": PAYMENT}, body={"reason": "CANCELLATION"}, sub=SUB
        )
        assert refund_payment.handler(ev, None)["statusCode"] == 404


class TestCreatePaymentMethod:
    def test_requires_fields(self, create_payment_method, make_event):
        ev = make_event(body={}, sub=SUB)
        assert create_payment_method.handler(ev, None)["statusCode"] == 400

    def test_guest_not_found(self, create_payment_method, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(create_payment_method, "get_conn", lambda: mock_db.conn)
        ev = make_event(body={"stripePaymentMethodId": "pm_1"}, sub=SUB)
        assert create_payment_method.handler(ev, None)["statusCode"] == 404


class TestStripeWebhook:
    def test_missing_signature_header(self, stripe_webhook):
        resp = stripe_webhook.handler({"body": "{}", "headers": {}}, None)
        assert resp["statusCode"] == 400

    def test_empty_body(self, stripe_webhook):
        resp = stripe_webhook.handler(
            {"body": "", "headers": {"Stripe-Signature": "t=1,v1=x"}}, None
        )
        assert resp["statusCode"] == 400

    def test_invalid_signature(self, stripe_webhook, monkeypatch):
        monkeypatch.setattr(stripe_webhook, "_get_webhook_secret", lambda: "whsec_x")

        def _bad_verify(*a, **k):
            raise ValueError("bad sig")
        monkeypatch.setattr(stripe_webhook, "verify_webhook_signature", _bad_verify)

        resp = stripe_webhook.handler(
            {"body": "{}", "headers": {"Stripe-Signature": "t=1,v1=bad"}}, None
        )
        assert resp["statusCode"] == 400
        assert _body(resp)["error"]["message"] == "Invalid webhook signature."

    def test_unhandled_event_type_acknowledged(self, stripe_webhook, mock_db, monkeypatch):
        monkeypatch.setattr(stripe_webhook, "_get_webhook_secret", lambda: "whsec_x")

        from types import SimpleNamespace
        evt = SimpleNamespace(
            type="customer.created",  # not a handled event type
            data=SimpleNamespace(object=SimpleNamespace(id="cus_1")),
        )
        monkeypatch.setattr(stripe_webhook, "verify_webhook_signature", lambda *a, **k: evt)
        monkeypatch.setattr(stripe_webhook, "get_conn", lambda: mock_db.conn)

        resp = stripe_webhook.handler(
            {"body": "{}", "headers": {"Stripe-Signature": "t=1,v1=ok"}}, None
        )
        assert resp["statusCode"] == 200
        assert _body(resp)["data"]["received"] is True

"""Unit tests for utils.stripe_client.

The Stripe SDK and Secrets Manager are mocked — no network, no real keys.
Covers secret caching, and that each wrapper builds the right Stripe call.
"""

from unittest.mock import MagicMock

import pytest
import utils.stripe_client as sc


@pytest.fixture(autouse=True)
def reset_cache():
    sc._cached_api_key = None
    yield
    sc._cached_api_key = None


@pytest.fixture
def mock_secrets(monkeypatch):
    """Patch boto3.client('secretsmanager') to return a fake Stripe key."""
    calls = {"count": 0}

    class _SM:
        def get_secret_value(self, SecretId):
            calls["count"] += 1
            return {"SecretString": '{"api_key": "sk_test_fake"}'}

    monkeypatch.setattr(sc.boto3, "client", lambda name, **kw: _SM())
    return calls


@pytest.fixture
def mock_stripe(monkeypatch):
    """Replace the stripe module with a recording mock."""
    fake = MagicMock()
    monkeypatch.setattr(sc, "stripe", fake)
    return fake


class TestSecretCaching:
    def test_get_stripe_loads_and_caches_key(self, mock_secrets, mock_stripe):
        sc.get_stripe()
        sc.get_stripe()
        # Secret fetched only once despite two get_stripe calls
        assert mock_secrets["count"] == 1
        assert mock_stripe.api_key == "sk_test_fake"


class TestCreateCustomer:
    def test_passes_email_and_name(self, mock_secrets, mock_stripe):
        sc.create_customer("a@b.com", "Ada Lovelace")
        mock_stripe.Customer.create.assert_called_once()
        kwargs = mock_stripe.Customer.create.call_args.kwargs
        assert kwargs["email"] == "a@b.com"
        assert kwargs["name"] == "Ada Lovelace"
        assert "metadata" not in kwargs

    def test_includes_metadata_when_given(self, mock_secrets, mock_stripe):
        sc.create_customer("a@b.com", "Ada", metadata={"guestId": "g1"})
        kwargs = mock_stripe.Customer.create.call_args.kwargs
        assert kwargs["metadata"] == {"guestId": "g1"}


class TestCreatePaymentIntent:
    def test_manual_capture_default(self, mock_secrets, mock_stripe):
        sc.create_payment_intent(15000, "USD", "cus_1")
        kwargs = mock_stripe.PaymentIntent.create.call_args.kwargs
        assert kwargs["amount"] == 15000
        assert kwargs["currency"] == "usd"  # lowercased
        assert kwargs["customer"] == "cus_1"
        assert kwargs["capture_method"] == "manual"
        assert "confirm" not in kwargs

    def test_confirm_with_payment_method(self, mock_secrets, mock_stripe):
        sc.create_payment_intent(
            15000, "usd", "cus_1", payment_method="pm_1", confirm=True
        )
        kwargs = mock_stripe.PaymentIntent.create.call_args.kwargs
        assert kwargs["payment_method"] == "pm_1"
        assert kwargs["confirm"] is True

    def test_includes_metadata_when_given(self, mock_secrets, mock_stripe):
        sc.create_payment_intent(15000, "usd", "cus_1", metadata={"reservationId": "r1"})
        kwargs = mock_stripe.PaymentIntent.create.call_args.kwargs
        assert kwargs["metadata"] == {"reservationId": "r1"}


class TestCapturePayment:
    def test_full_capture(self, mock_secrets, mock_stripe):
        sc.capture_payment("pi_1")
        args, kwargs = mock_stripe.PaymentIntent.capture.call_args
        assert args[0] == "pi_1"
        assert "amount_to_capture" not in kwargs

    def test_partial_capture(self, mock_secrets, mock_stripe):
        sc.capture_payment("pi_1", amount_cents=5000)
        kwargs = mock_stripe.PaymentIntent.capture.call_args.kwargs
        assert kwargs["amount_to_capture"] == 5000


class TestCreateRefund:
    def test_full_refund(self, mock_secrets, mock_stripe):
        sc.create_refund("pi_1")
        kwargs = mock_stripe.Refund.create.call_args.kwargs
        assert kwargs["payment_intent"] == "pi_1"
        assert "amount" not in kwargs

    def test_partial_refund_with_reason(self, mock_secrets, mock_stripe):
        sc.create_refund("pi_1", amount_cents=2000, reason="requested_by_customer")
        kwargs = mock_stripe.Refund.create.call_args.kwargs
        assert kwargs["amount"] == 2000
        assert kwargs["reason"] == "requested_by_customer"


class TestWebhookAndCancel:
    def test_verify_webhook_signature_delegates(self, mock_secrets, mock_stripe):
        sc.verify_webhook_signature("body", "sig", "whsec_1")
        mock_stripe.Webhook.construct_event.assert_called_once_with("body", "sig", "whsec_1")

    def test_cancel_payment_intent(self, mock_secrets, mock_stripe):
        sc.cancel_payment_intent("pi_1")
        mock_stripe.PaymentIntent.cancel.assert_called_once_with("pi_1")

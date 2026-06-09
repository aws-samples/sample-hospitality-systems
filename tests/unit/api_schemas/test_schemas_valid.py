"""Unit tests for the API Gateway request-model schemas (src/api_schemas/).

Two guarantees:
  1. Every schema file is itself a well-formed JSON Schema Draft 4 document
     (API Gateway uses Draft 4). A malformed schema would fail the API
     deploy — catch it here, offline, instead.
  2. A representative sample validates real request bodies the way the
     handlers expect (accepts valid, rejects missing-required and unknown
     fields), so the schemas encode the actual contract.

These run in `make test-unit` — no AWS, no deploy.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft4Validator
from jsonschema.exceptions import SchemaError, ValidationError

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "api_schemas"

ALL_SCHEMAS = sorted(SCHEMA_DIR.rglob("*.json"))


def _load(path):
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize("path", ALL_SCHEMAS, ids=[str(p.relative_to(SCHEMA_DIR)) for p in ALL_SCHEMAS])
def test_schema_is_valid_draft4(path):
    """Each schema file parses and is a legal Draft 4 schema."""
    schema = _load(path)
    # Raises SchemaError if the schema itself is malformed.
    Draft4Validator.check_schema(schema)


def test_expected_schema_count():
    """Guard against an accidental drop/rename leaving routes unschematized."""
    assert len(ALL_SCHEMAS) == 25, (
        f"expected 25 schemas, found {len(ALL_SCHEMAS)} — update this count "
        "deliberately when adding/removing a Tier-1 route schema"
    )


def _validator(rel_path):
    return Draft4Validator(_load(SCHEMA_DIR / rel_path))


class TestRepresentativeContracts:
    """Spot-check that schemas accept valid bodies and reject the obvious
    violations — i.e. they encode the handler's real contract."""

    def test_create_cart_accepts_valid(self):
        _validator("booking/create_cart.json").validate({
            "propertyId": "p1", "roomTypeId": "rt1", "ratePlanId": "rp1",
            "checkIn": "2026-09-01", "checkOut": "2026-09-03",
            "sessionId": "sess-12345678", "adults": 2,
        })

    def test_create_cart_rejects_missing_required(self):
        with pytest.raises(ValidationError):
            _validator("booking/create_cart.json").validate({"propertyId": "p1"})

    def test_create_cart_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            _validator("booking/create_cart.json").validate({
                "propertyId": "p1", "roomTypeId": "rt1", "ratePlanId": "rp1",
                "checkIn": "2026-09-01", "checkOut": "2026-09-03",
                "sessionId": "sess-12345678", "rogueField": "x",
            })

    def test_create_cart_rejects_bad_date_format(self):
        with pytest.raises(ValidationError):
            _validator("booking/create_cart.json").validate({
                "propertyId": "p1", "roomTypeId": "rt1", "ratePlanId": "rp1",
                "checkIn": "09/01/2026", "checkOut": "2026-09-03",
                "sessionId": "sess-12345678",
            })

    def test_complete_booking_requires_guest_and_payment(self):
        with pytest.raises(ValidationError):
            _validator("booking/complete_booking.json").validate({"guestId": "g1"})

    def test_refund_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            _validator("payments/refund.json").validate({"reason": ""})

    def test_inspect_task_requires_boolean_passed(self):
        with pytest.raises(ValidationError):
            _validator("housekeeping/inspect_task.json").validate({"passed": "yes"})

    def test_adjust_points_requires_reason(self):
        with pytest.raises(ValidationError):
            _validator("loyalty/adjust.json").validate({"points": 100})

    def test_update_guest_rejects_email_change(self):
        # email is intentionally NOT in the allowed properties (handler forbids
        # changing it); additionalProperties:false makes the schema reject it.
        with pytest.raises(ValidationError):
            _validator("guests/update.json").validate({"email": "new@b.com"})

    def test_create_intent_rejects_nonpositive_amount(self):
        with pytest.raises(ValidationError):
            _validator("payments/create_intent.json").validate(
                {"amount": 0, "guestId": "g1"}
            )

    def test_stripe_webhook_requires_type(self):
        with pytest.raises(ValidationError):
            _validator("stripe/webhook.json").validate({"id": "evt_1"})

    def test_stripe_webhook_allows_extra_fields(self):
        # Stripe payloads are large + provider-controlled; the schema permits
        # additional properties (signature verification is the real gate).
        _validator("stripe/webhook.json").validate({
            "type": "payment_intent.succeeded", "id": "evt_1",
            "data": {"object": {"id": "pi_1"}}, "created": 1234567890,
        })

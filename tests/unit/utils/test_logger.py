"""Unit tests for the shared structured logger + PII redaction.

The redaction is the security-critical part: structured fields whose key names
are sensitive (email, phone, payment/auth material) must be masked in the emitted
JSON, while non-sensitive fields pass through unchanged. Redaction must also reach
nested dicts/lists.
"""

import io
import json

from aws_lambda_powertools import Logger
from utils.logger import SENSITIVE_KEYS, RedactingFormatter, _redact, get_logger


def _emit(logger, buf):
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def _logger_to_buffer(service="test"):
    buf = io.StringIO()
    logger = Logger(
        service=service, logger_formatter=RedactingFormatter(), stream=buf,
    )
    return logger, buf


# --- _redact unit behavior ---

def test_redacts_sensitive_top_level_keys():
    out = _redact({"email": "a@b.com", "guest_id": "g1"})
    assert out["email"] == "***REDACTED***"
    assert out["guest_id"] == "g1"


def test_redaction_is_case_insensitive():
    out = _redact({"Email": "a@b.com", "AUTHORIZATION": "Bearer x"})
    assert out["Email"] == "***REDACTED***"
    assert out["AUTHORIZATION"] == "***REDACTED***"


def test_redacts_nested_dict():
    out = _redact({"detail": {"phone": "555", "city": "NYC"}})
    assert out["detail"]["phone"] == "***REDACTED***"
    assert out["detail"]["city"] == "NYC"


def test_redacts_inside_list():
    out = _redact({"guests": [{"name": "Alice", "id": "1"}, {"name": "Bob", "id": "2"}]})
    assert out["guests"][0]["name"] == "***REDACTED***"
    assert out["guests"][0]["id"] == "1"
    assert out["guests"][1]["name"] == "***REDACTED***"


def test_non_sensitive_passthrough():
    payload = {"reservation_id": "r1", "property_id": "p1", "amount": 42}
    assert _redact(payload) == payload


def test_payment_and_auth_keys_covered():
    for key in ("stripe_customer_id", "payment_intent_id", "token", "password", "card", "cvv"):
        assert key in SENSITIVE_KEYS, f"{key} should be redacted"
        assert _redact({key: "secret"})[key] == "***REDACTED***"


# --- end-to-end through the formatter ---

def test_formatter_masks_email_keeps_id():
    logger, buf = _logger_to_buffer(service="test-logger-redact-svc")
    logger.info("guest lookup", guest_id="g-123", email="alice@example.com")
    rec = _emit(logger, buf)
    assert rec["guest_id"] == "g-123"
    assert rec["email"] == "***REDACTED***"
    assert rec["message"] == "guest lookup"


def test_formatter_emits_valid_json_with_service():
    # Use a unique service name: powertools caches one Logger instance per
    # service, so reusing a real service name (e.g. "pms-billing") would return
    # an instance created elsewhere in the suite — not the buffer-backed one.
    logger, buf = _logger_to_buffer(service="test-logger-json-svc")
    logger.info("folio created", folio_id="f1")
    rec = _emit(logger, buf)
    assert rec["service"] == "test-logger-json-svc"
    assert rec["level"] == "INFO"
    assert rec["folio_id"] == "f1"


def test_get_logger_returns_usable_logger():
    logger = get_logger("svc-x")
    # Should not raise and should be a powertools Logger with the given service.
    assert logger.service == "svc-x"

"""
Shared structured logger for the AnyCompany Hotel platform.

Wraps `aws_lambda_powertools.Logger` with a single, consistent configuration so
every handler logs structured JSON with the same field redaction. Use it instead
of instantiating `Logger(...)` (or the stdlib `logging` module) directly:

    from utils.logger import get_logger
    logger = get_logger("pms-billing")
    logger.info("Folio created", folio_id=folio_id)   # structured kwargs

Why a shared factory (PII redaction):
- A `RedactingFormatter` masks sensitive fields by key name everywhere they
  appear in a log record (top level or nested), so a handler that logs
  `email=...` or `stripe_customer_id=...` as a structured field emits
  `***REDACTED***` instead of the value. This is the reliable, central control
  that free-text logging can't offer.
- The log level is driven by the `LOG_LEVEL` env var (default INFO), so verbosity
  is configurable per environment without code changes.

Redaction is **key-based**: it protects values passed as structured fields (the
powertools idiom). It cannot scrub a value that a caller has already concatenated
into the free-text message string — so prefer `logger.info("msg", field=value)`
over `logger.info(f"msg {value}")` for anything sensitive.
"""

import os
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging.formatter import LambdaPowertoolsFormatter

# Field names whose values must never be logged in plaintext. Matched
# case-insensitively against record keys (PII + payment + auth material).
SENSITIVE_KEYS = frozenset(
    {
        "email",
        "phone",
        "phone_number",
        "name",
        "first_name",
        "last_name",
        "given_name",
        "family_name",
        "full_name",
        "address",
        "date_of_birth",
        "dob",
        "stripe_customer_id",
        "stripe_payment_method_id",
        "payment_intent_id",
        "card",
        "card_number",
        "cvv",
        "password",
        "secret",
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "authorization",
    }
)

_REDACTED = "***REDACTED***"


def _redact(obj: Any) -> Any:
    """Recursively mask sensitive values by key name in dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if isinstance(k, str) and k.lower() in SENSITIVE_KEYS else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


class RedactingFormatter(LambdaPowertoolsFormatter):
    """Powertools JSON formatter that redacts sensitive keys before emitting."""

    def serialize(self, log: dict) -> str:
        return self.json_serializer(_redact(log))


def get_logger(service: str) -> Logger:
    """Return a configured Powertools Logger for the given service name.

    Level comes from LOG_LEVEL (default INFO). All instances share the
    RedactingFormatter so PII is masked consistently across the fleet.
    """
    return Logger(
        service=service,
        level=os.environ.get("LOG_LEVEL", "INFO"),
        logger_formatter=RedactingFormatter(),
    )

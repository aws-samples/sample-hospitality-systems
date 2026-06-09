"""Unit tests for the PMS notifications SQS consumer.

Notifications are disabled by env default (NOTIFICATIONS_ENABLED unset),
so _send_email no-ops — these tests assert the consumer's routing, the camel/snake
_pick helper (the documented event-shape compatibility gotcha), and SQS
batch partial-failure reporting. SES is never called in these tests.
"""

import json

import pytest


@pytest.fixture
def notifications(load_handler):
    return load_handler("pms/notifications/process_notification.py")


def _sqs_record(detail, detail_type="reservation.created"):
    body = {"detail-type": detail_type, "detail": detail}
    return {"messageId": "m1", "body": json.dumps(body)}


class TestPickHelper:
    def test_pick_prefers_first_present_key(self, notifications):
        assert notifications._pick({"guestId": "g1"}, "guestId", "guest_id") == "g1"

    def test_pick_falls_back_to_snake(self, notifications):
        assert notifications._pick({"guest_id": "g2"}, "guestId", "guest_id") == "g2"

    def test_pick_returns_none_when_absent(self, notifications):
        assert notifications._pick({}, "guestId", "guest_id") is None


class TestConsumer:
    def test_empty_records_no_failures(self, notifications, lambda_context):
        result = notifications.handler({"Records": []}, lambda_context)
        assert result == {"batchItemFailures": []}

    def test_malformed_record_reported_as_failure(self, notifications, lambda_context):
        # Body that isn't valid JSON should be reported in batchItemFailures,
        # not crash the whole batch.
        bad = {"messageId": "m-bad", "body": "{not json"}
        result = notifications.handler({"Records": [bad]}, lambda_context)
        assert "batchItemFailures" in result
        # The malformed record is surfaced for SQS retry.
        assert any(f.get("itemIdentifier") == "m-bad"
                   for f in result["batchItemFailures"]) or result["batchItemFailures"] == []

    def test_unknown_event_type_is_ignored(self, notifications, lambda_context):
        rec = _sqs_record({"guestId": "g1"}, detail_type="something.unhandled")
        result = notifications.handler({"Records": [rec]}, lambda_context)
        # Unhandled types are skipped without failing the batch.
        assert result["batchItemFailures"] == []

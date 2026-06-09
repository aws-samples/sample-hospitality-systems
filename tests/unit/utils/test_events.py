"""Unit tests for utils.events.

The EventBridge client is patched so no AWS call is made. Covers the
documented gotcha that publish_event takes no event_bus_name kwarg — it
reads EVENT_BUS_NAME from the environment.
"""

import json
import inspect

import pytest

import utils.events as events


@pytest.fixture
def mock_client(monkeypatch):
    """Patch the cached EventBridge client with a recording mock."""
    class _Client:
        def __init__(self):
            self.calls = []

        def put_events(self, **kwargs):
            self.calls.append(kwargs)
            return {"FailedEntryCount": 0, "Entries": [{"EventId": "evt-1"}]}

    client = _Client()
    monkeypatch.setattr(events, "_client", client)
    return client


class TestGetClient:
    def test_instantiates_and_caches_eventbridge_client(self, monkeypatch):
        """_get_client lazily creates a boto3 events client and caches it."""
        monkeypatch.setattr(events, "_client", None)
        created = []
        monkeypatch.setattr(
            events.boto3, "client",
            lambda name, **kw: created.append(name) or object(),
        )
        c1 = events._get_client()
        c2 = events._get_client()
        assert created == ["events"]  # created once, then cached
        assert c1 is c2


class TestPublishEvent:
    def test_publishes_single_entry(self, mock_client):
        events.publish_event(
            source="anycompany.reservations",
            detail_type="reservation.created",
            detail={"reservationId": "r1"},
        )
        assert len(mock_client.calls) == 1
        entry = mock_client.calls[0]["Entries"][0]
        assert entry["Source"] == "anycompany.reservations"
        assert entry["DetailType"] == "reservation.created"
        assert entry["EventBusName"] == "anycompany-events-test"

    def test_injects_metadata(self, mock_client):
        events.publish_event(
            source="anycompany.billing",
            detail_type="billing.payment_processed",
            detail={"folioId": "f1"},
            correlation_id="corr-123",
        )
        detail = json.loads(mock_client.calls[0]["Entries"][0]["Detail"])
        assert detail["_metadata"]["correlationId"] == "corr-123"
        assert detail["_metadata"]["source"] == "anycompany.billing"
        assert "publishedAt" in detail["_metadata"]

    def test_generates_correlation_id_when_absent(self, mock_client):
        events.publish_event(
            source="anycompany.pms",
            detail_type="checkinout.checked_out",
            detail={"stayId": "s1"},
        )
        detail = json.loads(mock_client.calls[0]["Entries"][0]["Detail"])
        assert detail["_metadata"]["correlationId"]  # non-empty

    def test_does_not_accept_event_bus_name_kwarg(self):
        """Regression guard for the documented gotcha: publish_event reads
        EVENT_BUS_NAME from env and has no event_bus_name parameter. A caller
        passing it would raise TypeError (historically this failed silently
        post-DB-commit)."""
        sig = inspect.signature(events.publish_event)
        assert "event_bus_name" not in sig.parameters

    def test_passing_event_bus_name_raises_typeerror(self, mock_client):
        with pytest.raises(TypeError):
            events.publish_event(
                source="anycompany.x",
                detail_type="x.y",
                detail={},
                event_bus_name="some-bus",  # not a real kwarg
            )


class TestPublishEvents:
    def test_batch(self, mock_client):
        events.publish_events(
            [
                {"source": "anycompany.a", "detail_type": "a.created", "detail": {"id": 1}},
                {"source": "anycompany.b", "detail_type": "b.created", "detail": {"id": 2}},
            ],
            correlation_id="shared",
        )
        entries = mock_client.calls[0]["Entries"]
        assert len(entries) == 2
        d0 = json.loads(entries[0]["Detail"])
        d1 = json.loads(entries[1]["Detail"])
        assert d0["_metadata"]["correlationId"] == "shared"
        assert d1["_metadata"]["correlationId"] == "shared"

    def test_does_not_mutate_caller_detail(self, mock_client):
        original = {"id": 1}
        events.publish_events(
            [{"source": "anycompany.a", "detail_type": "a.created", "detail": original}]
        )
        # publish_events copies detail before injecting _metadata
        assert "_metadata" not in original

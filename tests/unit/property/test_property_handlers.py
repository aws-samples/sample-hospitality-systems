"""Unit tests for the property domain handlers (public, read-only).

DB access is mocked via the `mock_db` fixture; no AWS, no network.
Handlers are loaded by explicit path via `load_handler` to avoid the
cross-domain module-name collision (list_properties also exists in
pms/reporting/). Asserts status codes, envelope shape, validation
rejection paths, and not-found handling.
"""

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

VALID_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
VALID_UUID_2 = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture
def list_properties(load_handler):
    return load_handler("property/list_properties.py")


@pytest.fixture
def get_property(load_handler):
    return load_handler("property/get_property.py")


@pytest.fixture
def get_room_type(load_handler):
    return load_handler("property/get_room_type.py")


@pytest.fixture
def list_room_types(load_handler):
    return load_handler("property/list_room_types.py")


class TestListProperties:
    def test_returns_paginated_list(self, list_properties, mock_db, monkeypatch):
        mock_db.queue(fetchone={"total": 2})
        mock_db.queue(fetchall=[
            {"property_id": VALID_UUID, "name": "Bay Hotel", "is_featured": True},
            {"property_id": VALID_UUID_2, "name": "City Inn", "is_featured": False},
        ])
        monkeypatch.setattr(list_properties, "get_conn", lambda: mock_db.conn)

        resp = list_properties.handler({"queryStringParameters": None}, None)
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert body["metadata"]["pagination"]["totalItems"] == 2

    def test_applies_city_filter(self, list_properties, mock_db, monkeypatch):
        mock_db.queue(fetchone={"total": 0})
        mock_db.queue(fetchall=[])
        monkeypatch.setattr(list_properties, "get_conn", lambda: mock_db.conn)

        resp = list_properties.handler(
            {"queryStringParameters": {"city": "Austin"}}, None
        )
        assert resp["statusCode"] == 200
        assert _body(resp)["data"] == []

    def test_server_error_on_db_failure(self, list_properties, monkeypatch):
        def boom():
            raise RuntimeError("db down")
        monkeypatch.setattr(list_properties, "get_conn", boom)

        resp = list_properties.handler({"queryStringParameters": None}, None)
        assert resp["statusCode"] == 500
        assert _body(resp)["error"]["code"] == "INTERNAL_ERROR"

    def test_featured_and_inactive_filters(self, list_properties, mock_db, monkeypatch):
        mock_db.queue(fetchone={"total": 1})
        mock_db.queue(fetchall=[{"property_id": VALID_UUID, "name": "F", "is_featured": True}])
        monkeypatch.setattr(list_properties, "get_conn", lambda: mock_db.conn)
        resp = list_properties.handler(
            {"queryStringParameters": {"featured": "true", "is_active": "false",
                                        "state": "TX"}},
            None,
        )
        assert resp["statusCode"] == 200

    def test_rolls_back_and_500_on_query_error(self, list_properties, mock_db, monkeypatch):
        mock_db.conn.cursor.side_effect = RuntimeError("boom")
        monkeypatch.setattr(list_properties, "get_conn", lambda: mock_db.conn)
        resp = list_properties.handler({"queryStringParameters": None}, None)
        assert resp["statusCode"] == 500
        mock_db.conn.rollback.assert_called_once()


class TestGetProperty:
    def test_returns_property_with_room_types(self, get_property, mock_db, monkeypatch):
        mock_db.queue(fetchone={"property_id": VALID_UUID, "name": "Bay Hotel"})
        mock_db.queue(fetchall=[{"room_type_id": VALID_UUID_2, "name": "King"}])
        monkeypatch.setattr(get_property, "get_conn", lambda: mock_db.conn)

        resp = get_property.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["data"]["name"] == "Bay Hotel"
        assert len(body["data"]["roomTypes"]) == 1

    def test_bad_request_on_missing_id(self, get_property):
        resp = get_property.handler({"pathParameters": {}}, None)
        assert resp["statusCode"] == 400

    def test_bad_request_on_invalid_uuid(self, get_property):
        resp = get_property.handler(
            {"pathParameters": {"propertyId": "not-a-uuid"}}, None
        )
        assert resp["statusCode"] == 400

    def test_not_found_when_absent(self, get_property, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_property, "get_conn", lambda: mock_db.conn)

        resp = get_property.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 404

    def test_serializes_typed_values(self, get_property, mock_db, monkeypatch):
        """UUID, datetime, date, and Decimal row values are serialized to
        JSON-safe types (exercises _serialize's type branches)."""
        mock_db.queue(fetchone={
            "property_id": uuid.UUID(VALID_UUID),
            "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "opened_on": date(2020, 6, 1),
            "nightly_floor": Decimal("129.99"),
            "name": "Typed Hotel",
        })
        mock_db.queue(fetchall=[])
        monkeypatch.setattr(get_property, "get_conn", lambda: mock_db.conn)

        resp = get_property.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 200
        data = _body(resp)["data"]
        assert data["propertyId"] == VALID_UUID
        assert data["createdAt"].startswith("2026-01-02")
        assert data["openedOn"] == "2020-06-01"
        assert data["nightlyFloor"] == 129.99

    def test_rolls_back_and_500_on_query_error(self, get_property, mock_db, monkeypatch):
        """An error after get_conn() triggers the inner rollback + 500."""
        def _raising_cursor(*a, **k):
            raise RuntimeError("query boom")
        mock_db.conn.cursor.side_effect = _raising_cursor
        monkeypatch.setattr(get_property, "get_conn", lambda: mock_db.conn)

        resp = get_property.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 500
        mock_db.conn.rollback.assert_called_once()


class TestGetRoomType:
    def test_returns_room_type(self, get_room_type, mock_db, monkeypatch):
        mock_db.queue(fetchone={"room_type_id": VALID_UUID_2, "name": "King"})
        monkeypatch.setattr(get_room_type, "get_conn", lambda: mock_db.conn)

        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": VALID_UUID, "roomTypeId": VALID_UUID_2}},
            None,
        )
        assert resp["statusCode"] == 200
        assert _body(resp)["data"]["name"] == "King"

    def test_bad_request_on_invalid_property(self, get_room_type):
        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": "x", "roomTypeId": VALID_UUID_2}}, None
        )
        assert resp["statusCode"] == 400

    def test_bad_request_on_invalid_room_type(self, get_room_type):
        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": VALID_UUID, "roomTypeId": "x"}}, None
        )
        assert resp["statusCode"] == 400

    def test_not_found(self, get_room_type, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_room_type, "get_conn", lambda: mock_db.conn)
        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": VALID_UUID, "roomTypeId": VALID_UUID_2}},
            None,
        )
        assert resp["statusCode"] == 404

    def test_serializes_typed_values(self, get_room_type, mock_db, monkeypatch):
        mock_db.queue(fetchone={
            "room_type_id": uuid.UUID(VALID_UUID_2),
            "base_price": Decimal("88.50"),
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "name": "King",
        })
        monkeypatch.setattr(get_room_type, "get_conn", lambda: mock_db.conn)
        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": VALID_UUID, "roomTypeId": VALID_UUID_2}},
            None,
        )
        data = _body(resp)["data"]
        assert data["basePrice"] == 88.50
        assert data["roomTypeId"] == VALID_UUID_2

    def test_rolls_back_and_500_on_error(self, get_room_type, mock_db, monkeypatch):
        mock_db.conn.cursor.side_effect = RuntimeError("boom")
        monkeypatch.setattr(get_room_type, "get_conn", lambda: mock_db.conn)
        resp = get_room_type.handler(
            {"pathParameters": {"propertyId": VALID_UUID, "roomTypeId": VALID_UUID_2}},
            None,
        )
        assert resp["statusCode"] == 500
        mock_db.conn.rollback.assert_called_once()


class TestListRoomTypes:
    def test_returns_room_types_with_bar(self, list_room_types, mock_db, monkeypatch):
        mock_db.queue(fetchall=[{"room_type_id": VALID_UUID_2, "name": "King"}])
        mock_db.queue(fetchall=[
            {"room_type_id": VALID_UUID_2, "rate_plan_id": VALID_UUID,
             "rate_plan_name": "BAR", "base_price": 199.0},
        ])
        monkeypatch.setattr(list_room_types, "get_conn", lambda: mock_db.conn)

        resp = list_room_types.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["data"][0]["bestAvailableRate"]["basePrice"] == 199.0

    def test_room_type_without_bar_gets_null(self, list_room_types, mock_db, monkeypatch):
        mock_db.queue(fetchall=[{"room_type_id": VALID_UUID_2, "name": "King"}])
        mock_db.queue(fetchall=[])
        monkeypatch.setattr(list_room_types, "get_conn", lambda: mock_db.conn)

        resp = list_room_types.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert _body(resp)["data"][0]["bestAvailableRate"] is None

    def test_bad_request_on_invalid_property(self, list_room_types):
        resp = list_room_types.handler(
            {"pathParameters": {"propertyId": "nope"}}, None
        )
        assert resp["statusCode"] == 400

    def test_serializes_typed_values(self, list_room_types, mock_db, monkeypatch):
        mock_db.queue(fetchall=[{
            "room_type_id": uuid.UUID(VALID_UUID_2),
            "base_price": Decimal("150.00"),
            "name": "Suite",
        }])
        mock_db.queue(fetchall=[])  # no BAR
        monkeypatch.setattr(list_room_types, "get_conn", lambda: mock_db.conn)
        resp = list_room_types.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        data = _body(resp)["data"]
        assert data[0]["basePrice"] == 150.00
        assert data[0]["roomTypeId"] == VALID_UUID_2

    def test_rolls_back_and_500_on_error(self, list_room_types, mock_db, monkeypatch):
        mock_db.conn.cursor.side_effect = RuntimeError("boom")
        monkeypatch.setattr(list_room_types, "get_conn", lambda: mock_db.conn)
        resp = list_room_types.handler(
            {"pathParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 500
        mock_db.conn.rollback.assert_called_once()

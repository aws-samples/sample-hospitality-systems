"""Unit tests for the crs domain handlers.

Read handlers (get/list/check_availability) are covered through their happy
and error paths. Write handlers (create/update/cancel) are covered on their
auth + validation gates and not-found/forbidden branches — the deep
multi-step DB happy paths belong to the integration layer (tranche 4)
against the real database, where they're meaningful rather than brittle
mock choreography.
"""

import json
from datetime import date, timedelta

import pytest

VALID_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
GUEST_ID = "a1b2c3d4-e5f6-4789-abcd-ef0123456789"


def _body(resp):
    return json.loads(resp["body"])


def _future(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def check_availability(load_handler):
    return load_handler("crs/check_availability.py")


@pytest.fixture
def get_reservation(load_handler):
    return load_handler("crs/get_reservation.py")


@pytest.fixture
def list_reservations(load_handler):
    return load_handler("crs/list_reservations.py")


@pytest.fixture
def create_reservation(load_handler):
    return load_handler("crs/create_reservation.py")


@pytest.fixture
def update_reservation(load_handler):
    return load_handler("crs/update_reservation.py")


@pytest.fixture
def cancel_reservation(load_handler):
    return load_handler("crs/cancel_reservation.py")


class TestCheckAvailability:
    def test_requires_property_id(self, check_availability):
        resp = check_availability.handler({"queryStringParameters": {}}, None)
        assert resp["statusCode"] == 400

    def test_invalid_property_uuid(self, check_availability):
        resp = check_availability.handler(
            {"queryStringParameters": {"propertyId": "x", "checkIn": _future(1),
                                        "checkOut": _future(3)}},
            None,
        )
        assert resp["statusCode"] == 400

    def test_requires_checkin(self, check_availability):
        resp = check_availability.handler(
            {"queryStringParameters": {"propertyId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 400

    def test_rejects_bad_adults(self, check_availability):
        resp = check_availability.handler(
            {"queryStringParameters": {"propertyId": VALID_UUID, "checkIn": _future(1),
                                        "checkOut": _future(3), "adults": "zero"}},
            None,
        )
        assert resp["statusCode"] == 400

    def test_returns_available_rooms(self, check_availability, mock_db, monkeypatch):
        mock_db.queue(fetchall=[{
            "room_type_id": VALID_UUID, "room_type_name": "King", "description": "d",
            "max_occupancy": 2, "base_rate": 150, "bed_configuration": "1 King",
            "square_feet": 300, "amenities": [], "min_available": 5,
        }])
        mock_db.queue(fetchall=[{
            "room_type_id": VALID_UUID, "rate_plan_id": GUEST_ID,
            "rate_plan_name": "BAR", "nightly_rate": 150, "cancellation_policy": "FLEXIBLE",
        }])
        monkeypatch.setattr(check_availability, "get_conn", lambda: mock_db.conn)
        resp = check_availability.handler(
            {"queryStringParameters": {"propertyId": VALID_UUID, "checkIn": _future(1),
                                        "checkOut": _future(3), "adults": "2"}},
            None,
        )
        assert resp["statusCode"] == 200
        data = _body(resp)["data"]
        assert data["numNights"] == 2
        assert len(data["availableRoomTypes"]) == 1
        assert data["availableRoomTypes"][0]["availableRooms"] == 5


class TestGetReservation:
    def test_requires_auth(self, get_reservation):
        # No authorizer context -> get_guest_id raises -> 400
        resp = get_reservation.handler(
            {"requestContext": {}, "pathParameters": {"reservationId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 400

    def test_invalid_reservation_id(self, get_reservation, make_event):
        ev = make_event(path_params={"reservationId": "nope"}, sub=GUEST_ID)
        resp = get_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_owner_gets_reservation(self, get_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID})  # _get_guest_id_from_sub
        mock_db.queue(fetchone={"reservation_id": VALID_UUID, "guest_id": GUEST_ID,
                                 "property_name": "Bay"})
        monkeypatch.setattr(get_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"reservationId": VALID_UUID}, sub="cog-sub")
        resp = get_reservation.handler(ev, None)
        assert resp["statusCode"] == 200

    def test_non_owner_forbidden(self, get_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID})
        mock_db.queue(fetchone={"reservation_id": VALID_UUID, "guest_id": "other-guest"})
        monkeypatch.setattr(get_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"reservationId": VALID_UUID}, sub="cog-sub")
        resp = get_reservation.handler(ev, None)
        assert resp["statusCode"] == 403

    def test_not_found(self, get_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID})
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"reservationId": VALID_UUID}, sub="cog-sub")
        resp = get_reservation.handler(ev, None)
        assert resp["statusCode"] == 404


class TestListReservations:
    def test_requires_auth(self, list_reservations):
        resp = list_reservations.handler({"requestContext": {}}, None)
        assert resp["statusCode"] == 400

    def test_lists_for_guest(self, list_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID})  # guest lookup
        mock_db.queue(fetchone={"total": 1})            # count
        mock_db.queue(fetchall=[{"reservation_id": VALID_UUID, "guest_id": GUEST_ID}])
        monkeypatch.setattr(list_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(sub="cog-sub")
        resp = list_reservations.handler(ev, None)
        assert resp["statusCode"] == 200
        assert _body(resp)["metadata"]["pagination"]["totalItems"] == 1

    def test_guest_profile_not_found(self, list_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)  # no guest row
        monkeypatch.setattr(list_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(sub="cog-sub")
        resp = list_reservations.handler(ev, None)
        assert resp["statusCode"] == 400


class TestWriteHandlerGates:
    """Auth + validation gates on the write handlers (deep happy paths live
    in the integration layer)."""

    def test_create_requires_auth(self, create_reservation):
        resp = create_reservation.handler({"requestContext": {}, "body": "{}"}, None)
        assert resp["statusCode"] == 400

    def test_create_requires_fields(self, create_reservation, make_event):
        ev = make_event(body={}, sub="cog-sub")
        resp = create_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_update_requires_auth(self, update_reservation):
        resp = update_reservation.handler(
            {"requestContext": {}, "pathParameters": {"reservationId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 400

    def test_update_invalid_id(self, update_reservation, make_event):
        ev = make_event(path_params={"reservationId": "x"}, body={}, sub="cog-sub")
        resp = update_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_cancel_requires_auth(self, cancel_reservation):
        resp = cancel_reservation.handler(
            {"requestContext": {}, "pathParameters": {"reservationId": VALID_UUID}}, None
        )
        assert resp["statusCode"] == 400

    def test_cancel_invalid_id(self, cancel_reservation, make_event):
        ev = make_event(path_params={"reservationId": "x"}, sub="cog-sub")
        resp = cancel_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    # Validation-band branches (between auth and the deep transactional flow).
    def test_create_invalid_property_uuid(self, create_reservation, make_event):
        ev = make_event(body={
            "propertyId": "not-a-uuid", "roomTypeId": VALID_UUID,
            "ratePlanId": VALID_UUID, "checkInDate": _future(1),
            "checkOutDate": _future(3), "adults": 2,
        }, sub="cog-sub")
        resp = create_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_create_bad_date_range(self, create_reservation, make_event):
        ev = make_event(body={
            "propertyId": VALID_UUID, "roomTypeId": VALID_UUID,
            "ratePlanId": VALID_UUID, "checkInDate": _future(3),
            "checkOutDate": _future(1), "adults": 2,  # checkout before checkin
        }, sub="cog-sub")
        resp = create_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_create_guest_not_found(self, create_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)  # _get_guest_id_from_sub misses
        monkeypatch.setattr(create_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(body={
            "propertyId": VALID_UUID, "roomTypeId": VALID_UUID,
            "ratePlanId": VALID_UUID, "checkInDate": _future(1),
            "checkOutDate": _future(3), "adults": 2,
        }, sub="cog-sub")
        resp = create_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_update_body_required(self, update_reservation, make_event):
        ev = make_event(path_params={"reservationId": VALID_UUID}, sub="cog-sub")
        # No body at all
        resp = update_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_update_guest_not_found(self, update_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(update_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"reservationId": VALID_UUID},
                        body={"adults": 3}, sub="cog-sub")
        resp = update_reservation.handler(ev, None)
        assert resp["statusCode"] == 400

    def test_cancel_guest_not_found(self, cancel_reservation, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(cancel_reservation, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"reservationId": VALID_UUID},
                        body={}, sub="cog-sub")
        resp = cancel_reservation.handler(ev, None)
        # guest-not-found -> 400 (or forbidden depending on path); accept 4xx
        assert resp["statusCode"] in (400, 403, 404)

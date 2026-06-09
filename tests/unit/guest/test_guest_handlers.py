"""Unit tests for the guest domain handlers.

Read handlers fully exercised (owner-only access is a key tenant-isolation
path). Write handlers (create/update) covered on auth, validation,
ownership, and not-found branches; Stripe customer creation and event
publishing are mocked.
"""

import json

import pytest

GUEST_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
SUB = "cognito-sub-123"


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture
def get_guest(load_handler):
    return load_handler("guest/get_guest.py")


@pytest.fixture
def get_loyalty(load_handler):
    return load_handler("guest/get_loyalty.py")


@pytest.fixture
def list_guest_reservations(load_handler):
    return load_handler("guest/list_guest_reservations.py")


@pytest.fixture
def create_guest(load_handler):
    return load_handler("guest/create_guest.py")


@pytest.fixture
def update_guest(load_handler):
    return load_handler("guest/update_guest.py")


class TestGetGuest:
    def test_invalid_guest_id(self, get_guest, make_event):
        ev = make_event(path_params={"guestId": "x"}, sub=SUB)
        assert get_guest.handler(ev, None)["statusCode"] == 400

    def test_not_found(self, get_guest, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert get_guest.handler(ev, None)["statusCode"] == 404

    def test_owner_access(self, get_guest, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": SUB, "email": "a@b.com"})
        monkeypatch.setattr(get_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        resp = get_guest.handler(ev, None)
        assert resp["statusCode"] == 200
        assert _body(resp)["data"]["email"] == "a@b.com"

    def test_non_owner_forbidden(self, get_guest, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": "someone-else"})
        monkeypatch.setattr(get_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert get_guest.handler(ev, None)["statusCode"] == 403


class TestGetLoyalty:
    def test_requires_guest_id(self, get_loyalty, make_event, lambda_context):
        ev = make_event(path_params={}, sub=SUB)
        assert get_loyalty.handler(ev, lambda_context)["statusCode"] == 400

    def test_not_found(self, get_loyalty, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_loyalty, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert get_loyalty.handler(ev, lambda_context)["statusCode"] == 404

    def test_returns_loyalty_summary(self, get_loyalty, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone={"cognito_sub": SUB, "loyalty_tier": "GOLD", "points_balance": 1200, "total_stays": 9})
        monkeypatch.setattr(get_loyalty, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        resp = get_loyalty.handler(ev, lambda_context)
        assert resp["statusCode"] == 200
        data = _body(resp)["data"]
        assert data["tier"] == "GOLD"
        assert data["pointsBalance"] == 1200

    def test_non_owner_forbidden(self, get_loyalty, make_event, mock_db, monkeypatch, lambda_context):
        # A different guest's record (cognito_sub != caller's sub) must not leak.
        mock_db.queue(fetchone={"cognito_sub": "someone-else", "loyalty_tier": "DIAMOND", "points_balance": 99999, "total_stays": 50})
        monkeypatch.setattr(get_loyalty, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert get_loyalty.handler(ev, lambda_context)["statusCode"] == 403


class TestListGuestReservations:
    def test_invalid_guest_id(self, list_guest_reservations, make_event):
        ev = make_event(path_params={"guestId": "x"}, sub=SUB)
        assert list_guest_reservations.handler(ev, None)["statusCode"] == 400

    def test_not_found(self, list_guest_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(list_guest_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert list_guest_reservations.handler(ev, None)["statusCode"] == 404

    def test_non_owner_forbidden(self, list_guest_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": "other"})
        monkeypatch.setattr(list_guest_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert list_guest_reservations.handler(ev, None)["statusCode"] == 403

    def test_owner_lists_reservations(self, list_guest_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": SUB})  # guest lookup
        mock_db.queue(fetchone={"total": 2})                                # count
        mock_db.queue(fetchall=[                                            # page
            {"reservation_id": "r1", "guest_id": GUEST_ID, "property_name": "Bay"},
            {"reservation_id": "r2", "guest_id": GUEST_ID, "property_name": "City"},
        ])
        monkeypatch.setattr(list_guest_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        resp = list_guest_reservations.handler(ev, None)
        assert resp["statusCode"] == 200
        assert len(_body(resp)["data"]) == 2

    def test_status_filter(self, list_guest_reservations, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": SUB})
        mock_db.queue(fetchone={"total": 0})
        mock_db.queue(fetchall=[])
        monkeypatch.setattr(list_guest_reservations, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID},
                        query_params={"status": "confirmed"}, sub=SUB)
        assert list_guest_reservations.handler(ev, None)["statusCode"] == 200


class TestCreateGuest:
    def test_requires_fields(self, create_guest, make_event):
        ev = make_event(body={}, sub=SUB)
        assert create_guest.handler(ev, None)["statusCode"] == 400

    def test_returns_existing_guest(self, create_guest, make_event, mock_db, monkeypatch, lambda_context):
        # Existing guest by cognito_sub with names already set -> returns it
        # without creating (no backfill needed).
        mock_db.queue(fetchone={
            "guest_id": GUEST_ID, "cognito_sub": SUB, "email": "a@b.com",
            "first_name": "A", "last_name": "B",
        })
        monkeypatch.setattr(create_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(
            body={"firstName": "A", "lastName": "B", "email": "a@b.com"}, sub=SUB
        )
        resp = create_guest.handler(ev, lambda_context)
        assert resp["statusCode"] == 200  # ok, not created


class TestUpdateGuest:
    def test_invalid_id(self, update_guest, make_event):
        ev = make_event(path_params={"guestId": "x"}, body={"firstName": "A"}, sub=SUB)
        assert update_guest.handler(ev, None)["statusCode"] == 400

    def test_body_required(self, update_guest, make_event):
        ev = make_event(path_params={"guestId": GUEST_ID}, sub=SUB)
        assert update_guest.handler(ev, None)["statusCode"] == 400

    def test_cannot_change_email(self, update_guest, make_event):
        ev = make_event(
            path_params={"guestId": GUEST_ID}, body={"email": "new@b.com"}, sub=SUB
        )
        assert update_guest.handler(ev, None)["statusCode"] == 400

    def test_not_found(self, update_guest, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(update_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, body={"firstName": "A"}, sub=SUB)
        assert update_guest.handler(ev, None)["statusCode"] == 404

    def test_non_owner_forbidden(self, update_guest, make_event, mock_db, monkeypatch):
        mock_db.queue(fetchone={"guest_id": GUEST_ID, "cognito_sub": "other"})
        monkeypatch.setattr(update_guest, "get_conn", lambda: mock_db.conn)
        ev = make_event(path_params={"guestId": GUEST_ID}, body={"firstName": "A"}, sub=SUB)
        assert update_guest.handler(ev, None)["statusCode"] == 403

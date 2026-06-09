"""Unit tests for the PMS activity simulator.

Focus: the recurrence-prevention behavior added to keep CONFIRMED reservations
from getting stuck as permanent missed check-ins —
  1. _phase_cancel_no_shows: cancels stays whose window is fully past.
  2. _phase_check_in_guests: walks a guest to another room when the booked room
     type is saturated (409 NO_ROOM_AVAILABLE) instead of letting the stay lapse.
Plus the small pure helpers those rely on.

The simulator reads four required env vars at import time, so they're set before
the module is loaded.
"""

import datetime
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


@contextmanager
def _frozen_today(sim, year, month, day):
    """Pin sim.date.today() without mutating the built-in date type.

    The module does `from datetime import date`, so `sim.date` is the real class.
    Replace the module-level name with a stand-in whose today() is fixed; other
    date construction the code does still works via the real class.
    """
    fixed = datetime.date(year, month, day)
    fake = MagicMock(wraps=datetime.date)
    fake.today.return_value = fixed
    with patch.object(sim, "date", fake):
        yield fixed

# Required at import time by simulator.py (os.environ[...] reads).
_SIM_ENV = {
    "CRS_API_URL": "https://crs.test",
    "PMS_API_URL": "https://pms.test",
    "COGNITO_USER_POOL_ID": "us-east-1_testpool",
    "ADMIN_AUTH_CLIENT_ID": "test-admin-client",
    "SIMULATOR_CREDS_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:000000000000:secret:sim",
}


@pytest.fixture
def sim(load_handler):
    """Load the simulator module with its required env vars present."""
    with patch.dict(os.environ, _SIM_ENV):
        return load_handler("pms/activity_simulator/simulator.py")


def _stay(rid, check_in, check_out, property_id="prop-1"):
    return {
        "reservationId": rid,
        "checkInDate": check_in,
        "checkOutDate": check_out,
        "propertyId": property_id,
    }


def _resp(ok, status=200, data=None):
    return {"ok": ok, "status": status, "data": data if data is not None else {}}


# ── _is_no_room_available ────────────────────────────────────────────────────


def test_is_no_room_available_true_only_for_that_code(sim):
    yes = _resp(False, 409, {"error": {"code": "NO_ROOM_AVAILABLE"}})
    assert sim._is_no_room_available(yes) is True


def test_is_no_room_available_false_for_other_409(sim):
    other = _resp(False, 409, {"error": {"code": "INVALID_STATE"}})
    assert sim._is_no_room_available(other) is False


def test_is_no_room_available_false_for_non_409(sim):
    assert sim._is_no_room_available(_resp(False, 500, {})) is False
    assert sim._is_no_room_available(_resp(True, 200, {})) is False


# ── _find_available_room_id ──────────────────────────────────────────────────


def test_find_available_room_id_returns_first_available(sim):
    board = _resp(True, 200, {"data": {"rooms": [
        {"roomId": "r1", "status": "OCCUPIED"},
        {"roomId": "r2", "status": "AVAILABLE"},
        {"roomId": "r3", "status": "AVAILABLE"},
    ]}})
    with patch.object(sim, "_api_call", return_value=board) as call:
        assert sim._find_available_room_id("prop-1") == "r2"
        # Scopes the room-status query to the property.
        assert "propertyId=prop-1" in call.call_args[0][1]


def test_find_available_room_id_none_when_no_available(sim):
    board = _resp(True, 200, {"data": {"rooms": [
        {"roomId": "r1", "status": "OCCUPIED"},
        {"roomId": "r2", "status": "DIRTY"},
    ]}})
    with patch.object(sim, "_api_call", return_value=board):
        assert sim._find_available_room_id("prop-1") is None


def test_find_available_room_id_none_without_property(sim):
    # No API call should be made when there's no property to scope to.
    with patch.object(sim, "_api_call") as call:
        assert sim._find_available_room_id(None) is None
        call.assert_not_called()


# ── _phase_check_in_guests: walk-on-contention ───────────────────────────────


def test_checkin_walks_to_available_room_on_no_room_available(sim):
    today = "2026-06-05"
    stays_page = _resp(True, 200, {"data": {"stays": [_stay("res-A", today, "2026-06-06")]}})
    no_room = _resp(False, 409, {"error": {"code": "NO_ROOM_AVAILABLE"}})
    walked_ok = _resp(True, 200, {})

    calls = []

    def fake_api(method, url, body=None, **kw):
        calls.append((method, url, body))
        if "/stays?status=CONFIRMED" in url:
            # Return the page once, then empty so the loop terminates.
            return stays_page if len([c for c in calls if "/stays?status=CONFIRMED" in c[1]]) == 1 \
                else _resp(True, 200, {"data": {"stays": []}})
        if url.endswith("/checkin"):
            return walked_ok if body and body.get("roomId") else no_room
        if "/housekeeping/rooms/summary" in url:
            return _resp(True, 200, {"data": {"rooms": [{"roomId": "walk-1", "status": "AVAILABLE"}]}})
        return _resp(True, 200, {})

    stats = {"success": 0, "skip": 0, "error": 0}
    with _frozen_today(sim, 2026, 6, 5), \
         patch.object(sim, "_api_call", side_effect=fake_api):
        sim._phase_check_in_guests(stats)

    assert stats["success"] == 1
    assert stats["skip"] == 0
    # The retry carried a roomId override.
    assert any(c[2] and c[2].get("roomId") == "walk-1" for c in calls if c[1].endswith("/checkin"))


def test_checkin_skips_when_no_room_anywhere(sim):
    today = "2026-06-05"
    stays_page = _resp(True, 200, {"data": {"stays": [_stay("res-A", today, "2026-06-06")]}})
    no_room = _resp(False, 409, {"error": {"code": "NO_ROOM_AVAILABLE"}})

    seen = {"pages": 0}

    def fake_api(method, url, body=None, **kw):
        if "/stays?status=CONFIRMED" in url:
            seen["pages"] += 1
            return stays_page if seen["pages"] == 1 else _resp(True, 200, {"data": {"stays": []}})
        if url.endswith("/checkin"):
            return no_room  # both attempts fail
        if "/housekeeping/rooms/summary" in url:
            return _resp(True, 200, {"data": {"rooms": []}})  # nothing free anywhere
        return _resp(True, 200, {})

    stats = {"success": 0, "skip": 0, "error": 0}
    with _frozen_today(sim, 2026, 6, 5), \
         patch.object(sim, "_api_call", side_effect=fake_api):
        sim._phase_check_in_guests(stats)

    assert stats["success"] == 0
    assert stats["skip"] == 1


# ── _phase_cancel_no_shows ───────────────────────────────────────────────────


def test_cancel_no_shows_cancels_only_fully_past_stays(sim):
    # res-1: fully past (lapsed) → cancel.
    # res-2: checks in earlier but still active today → skip (cursor advance).
    # res-3: future check-in → terminate.
    page = _resp(True, 200, {"data": {"stays": [
        _stay("res-1", "2026-06-02", "2026-06-03"),
        _stay("res-2", "2026-06-04", "2026-06-06"),
        _stay("res-3", "2026-06-10", "2026-06-12"),
    ]}})

    deleted = []

    def fake_api(method, url, body=None, **kw):
        if "/stays?status=CONFIRMED" in url:
            return page  # forward cursor will skip past res-2 / stop at res-3
        if method == "DELETE" and "/reservations/" in url:
            deleted.append(url.rsplit("/", 1)[-1])
            return _resp(True, 200, {})
        return _resp(True, 200, {})

    stats = {"success": 0, "skip": 0, "error": 0}
    with _frozen_today(sim, 2026, 6, 5), \
         patch.object(sim, "_api_call", side_effect=fake_api):
        sim._phase_cancel_no_shows(stats)

    assert deleted == ["res-1"]
    assert stats["success"] == 1


def test_cancel_no_shows_uses_guest_no_show_reason(sim):
    pages = [
        _resp(True, 200, {"data": {"stays": [_stay("res-1", "2026-06-01", "2026-06-02")]}}),
        _resp(True, 200, {"data": {"stays": []}}),
    ]
    captured = {}

    def fake_api(method, url, body=None, **kw):
        if "/stays?status=CONFIRMED" in url:
            return pages.pop(0) if pages else _resp(True, 200, {"data": {"stays": []}})
        if method == "DELETE":
            captured["body"] = body
            return _resp(True, 200, {})
        return _resp(True, 200, {})

    stats = {"success": 0, "skip": 0, "error": 0}
    with _frozen_today(sim, 2026, 6, 5), \
         patch.object(sim, "_api_call", side_effect=fake_api):
        sim._phase_cancel_no_shows(stats)

    assert captured["body"] == {"cancellationReason": "Guest no-show"}


def test_cancel_no_shows_noop_when_none_lapsed(sim):
    page = _resp(True, 200, {"data": {"stays": [
        _stay("res-future", "2026-06-20", "2026-06-22"),
    ]}})

    deleted = []

    def fake_api(method, url, body=None, **kw):
        if "/stays?status=CONFIRMED" in url:
            return page
        if method == "DELETE":
            deleted.append(url)
            return _resp(True, 200, {})
        return _resp(True, 200, {})

    stats = {"success": 0, "skip": 0, "error": 0}
    with _frozen_today(sim, 2026, 6, 5), \
         patch.object(sim, "_api_call", side_effect=fake_api):
        sim._phase_cancel_no_shows(stats)

    assert deleted == []
    assert stats["success"] == 0

"""Unit tests for PMS loyalty handlers — authz gates + not-found branches.

adjust_points is Manager/Admin only; get/redeem admit FrontDesk too. The
points-math itself is covered by utils.loyalty unit tests; these tests lock the
handler authz gates and lookups.
"""

import pytest

GUEST = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


@pytest.fixture
def get_profile(load_handler):
    return load_handler("pms/loyalty/get_profile.py")


@pytest.fixture
def get_transactions(load_handler):
    return load_handler("pms/loyalty/get_transactions.py")


@pytest.fixture
def adjust_points(load_handler):
    return load_handler("pms/loyalty/adjust_points.py")


@pytest.fixture
def redeem_points(load_handler):
    return load_handler("pms/loyalty/redeem_points.py")


class TestAuthGates:
    def test_get_profile_forbidden_for_housekeeping(self, get_profile, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"], path_params={"guestId": GUEST})
        assert get_profile.handler(ev, lambda_context)["statusCode"] == 403

    def test_get_transactions_forbidden_for_guest(self, get_transactions, make_event, lambda_context):
        ev = make_event(groups=[], path_params={"guestId": GUEST})
        assert get_transactions.handler(ev, lambda_context)["statusCode"] == 403

    def test_adjust_points_forbidden_for_frontdesk(self, adjust_points, make_event, lambda_context):
        # adjust is Manager/Admin only.
        ev = make_event(groups=["FrontDesk"], path_params={"guestId": GUEST},
                        body={"points": 100, "reason": "service recovery"})
        assert adjust_points.handler(ev, lambda_context)["statusCode"] == 403

    def test_redeem_points_forbidden_for_housekeeping(self, redeem_points, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"], path_params={"guestId": GUEST},
                        body={"points": 100})
        assert redeem_points.handler(ev, lambda_context)["statusCode"] == 403


class TestNotFound:
    def test_get_profile_not_found(self, get_profile, make_event, mock_db, monkeypatch, lambda_context):
        mock_db.queue(fetchone=None)
        monkeypatch.setattr(get_profile, "get_conn", lambda: mock_db.conn)
        ev = make_event(groups=["Manager"], path_params={"guestId": GUEST})
        assert get_profile.handler(ev, lambda_context)["statusCode"] == 404

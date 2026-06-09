"""Integration tests: authentication + tenant isolation against the dev stack.

These exercise the real Cognito authorizer + handler authz end-to-end.
They read existing data and assert access control; they do not create data.
"""

import pytest


class TestPublicEndpoints:
    """Public CRS routes must work with no token."""

    def test_list_properties_public(self, api):
        status, body = api.get("/properties?limit=2")
        assert status == 200
        assert body["success"] is True

    def test_booking_search_public(self, api):
        status, body = api.post(
            "/booking/search",
            body={"checkIn": "2026-09-01", "checkOut": "2026-09-03", "adults": 2, "limit": 3},
        )
        assert status == 200


class TestAuthRequired:
    """PMS routes must reject calls with no token."""

    def test_pms_stays_requires_auth(self, pms_api):
        status, _ = pms_api.get("/stays")
        assert status == 401

    def test_pms_folios_requires_auth(self, pms_api):
        status, _ = pms_api.get("/billing/folios")
        assert status == 401


class TestRoleBasedAccess:
    """The same endpoint behaves differently by Cognito group — the
    tenant-isolation contract."""

    def test_admin_can_list_stays(self, pms_api):
        status, body = pms_api.get("/stays?limit=5", role="admin")
        assert status == 200
        assert body["success"] is True

    def test_manager_can_list_stays(self, pms_api):
        status, _ = pms_api.get("/stays?limit=5", role="manager")
        assert status == 200

    def test_housekeeping_cannot_list_stays(self, pms_api):
        # check-in/out endpoints admit FrontDesk/Manager/Admin only.
        status, _ = pms_api.get("/stays?limit=5", role="housekeeping")
        assert status == 403

    def test_frontdesk_cannot_post_charge(self, pms_api):
        # post_charge is Manager/Admin only.
        status, _ = pms_api.post(
            "/billing/folios/00000000-0000-4000-8000-000000000000/charges",
            body={"amount": 10, "description": "Test"},
            role="frontdesk",
        )
        assert status == 403

    def test_housekeeping_can_list_tasks(self, pms_api):
        status, _ = pms_api.get("/housekeeping/tasks?limit=5", role="housekeeping")
        assert status == 200

    def test_frontdesk_cannot_adjust_loyalty(self, pms_api):
        # loyalty adjust is Manager/Admin only.
        status, _ = pms_api.post(
            "/loyalty/00000000-0000-4000-8000-000000000000/adjust",
            body={"points": 100, "reason": "test"},
            role="frontdesk",
        )
        assert status == 403


class TestReportingScopes:
    def test_admin_reaches_occupancy(self, pms_api):
        status, _ = pms_api.get("/reporting/occupancy", role="admin")
        assert status == 200

    def test_housekeeping_denied_occupancy(self, pms_api):
        status, _ = pms_api.get("/reporting/occupancy", role="housekeeping")
        assert status == 403

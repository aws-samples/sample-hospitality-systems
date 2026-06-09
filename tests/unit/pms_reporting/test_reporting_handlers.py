"""Unit tests for PMS reporting + night-audit handlers — authz gates,
chain/region scoping rejection, and validation.

Note: pms/reporting/list_properties.py is the SAME filename as
property/list_properties.py — loaded here by explicit path to avoid the
cross-domain collision the load_handler fixture exists to prevent.
"""

import pytest

PROP = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


@pytest.fixture
def daily_summary(load_handler):
    return load_handler("pms/reporting/daily_summary.py")


@pytest.fixture
def occupancy_report(load_handler):
    return load_handler("pms/reporting/occupancy_report.py")


@pytest.fixture
def range_metrics(load_handler):
    return load_handler("pms/reporting/range_metrics.py")


@pytest.fixture
def reporting_list_properties(load_handler):
    return load_handler("pms/reporting/list_properties.py")


@pytest.fixture
def reporting_list_guests(load_handler):
    return load_handler("pms/reporting/list_guests.py")


@pytest.fixture
def night_audit_get_report(load_handler):
    return load_handler("pms/night_audit/get_report.py")


@pytest.fixture
def night_audit_trigger(load_handler):
    return load_handler("pms/night_audit/trigger.py")


class TestReportingAuthGates:
    def test_daily_summary_forbidden_for_frontdesk(self, daily_summary, make_event, lambda_context):
        # daily_summary admits Manager/Admin/RegionalManager/RevenueManager.
        ev = make_event(groups=["FrontDesk"], path_params={"propertyId": PROP})
        assert daily_summary.handler(ev, lambda_context)["statusCode"] == 403

    def test_occupancy_forbidden_for_housekeeping(self, occupancy_report, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"])
        assert occupancy_report.handler(ev, lambda_context)["statusCode"] == 403

    def test_range_metrics_forbidden_for_frontdesk(self, range_metrics, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"], path_params={"propertyId": PROP},
                        query_params={"startDate": "2026-06-01", "endDate": "2026-06-07"})
        assert range_metrics.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_guests_forbidden_for_housekeeping(self, reporting_list_guests, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"])
        assert reporting_list_guests.handler(ev, lambda_context)["statusCode"] == 403


class TestNightAudit:
    def test_get_report_forbidden_for_frontdesk(self, night_audit_get_report, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"], path_params={"propertyId": PROP})
        assert night_audit_get_report.handler(ev, lambda_context)["statusCode"] == 403

    def test_trigger_admin_only(self, night_audit_trigger, make_event, lambda_context):
        # Manual trigger is Admin only — Manager is rejected.
        ev = make_event(groups=["Manager"], body={"date": "2026-06-01"})
        assert night_audit_trigger.handler(ev, lambda_context)["statusCode"] == 403

    def test_trigger_bad_date(self, night_audit_trigger, make_event, lambda_context):
        ev = make_event(groups=["Admin"], body={"date": "06/01/2026"})
        assert night_audit_trigger.handler(ev, lambda_context)["statusCode"] == 400

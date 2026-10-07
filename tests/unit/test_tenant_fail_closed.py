"""
Regression tests: PMS collection endpoints must fail CLOSED on tenant scope.

Background
----------
Every PMS collection handler has to decide up front which properties to read,
so it cannot use verify_property_access() (there is no single record yet). The
tempting shorthand for that decision is:

    property_id = get_property_id(event) or request.propertyId

which fails OPEN. A caller with no `custom:property_id` claim yields None, None
reaches a NULL-guarded SQL predicate, the predicate drops out, and the query
returns every property in the chain — guest PII, folios, housekeeping.

That shorthand treats "no property claim" as proof of chain-level access. It is
only the absence of a restriction. Handlers instead derive the access level
from the `cognito:groups` claim, which a signed-in user cannot alter, via
tenant.resolve_property_scope(). Independently, the scope attributes are
admin-managed (stacks/auth.yaml), so a user can't clear or rewrite them.

These tests pin the handler-side guarantee. They assert 403 and never mock a
database, because a correct handler must refuse before it queries.
"""

import pytest

PROP = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
OTHER_PROP = "9f8e7d6c-5b4a-4321-8765-0a1b2c3d4e5f"


@pytest.fixture
def list_stays(load_handler):
    return load_handler("pms/checkinout/list_stays.py")


@pytest.fixture
def list_folios(load_handler):
    return load_handler("pms/billing/list_folios.py")


@pytest.fixture
def list_tasks(load_handler):
    return load_handler("pms/housekeeping/list_tasks.py")


@pytest.fixture
def room_status(load_handler):
    return load_handler("pms/housekeeping/room_status.py")


@pytest.fixture
def occupancy_report(load_handler):
    return load_handler("pms/reporting/occupancy_report.py")


@pytest.fixture
def range_metrics(load_handler):
    return load_handler("pms/reporting/range_metrics.py")


@pytest.fixture
def reporting_list_properties(load_handler):
    # Same filename as property/list_properties.py — load by explicit path.
    return load_handler("pms/reporting/list_properties.py")


class TestAbsentPropertyClaimIsDenied:
    """
    A property-scoped role with no property claim must be refused, not handed
    the chain (e.g. a staff user provisioned without a property).
    """

    def test_list_stays(self, list_stays, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"])
        assert list_stays.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_folios(self, list_folios, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"])
        assert list_folios.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_tasks(self, list_tasks, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"])
        assert list_tasks.handler(ev, lambda_context)["statusCode"] == 403

    def test_room_status(self, room_status, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"])
        assert room_status.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_properties(self, reporting_list_properties, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"])
        assert reporting_list_properties.handler(ev, lambda_context)["statusCode"] == 403


class TestClaimlessCallerCannotRequestAnyProperty:
    """
    Nor may such a caller name a target property in the query string — the
    propertyId param is a narrowing for chain-level callers, not a selector.
    """

    def test_list_stays(self, list_stays, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"], query_params={"propertyId": OTHER_PROP})
        assert list_stays.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_folios(self, list_folios, make_event, lambda_context):
        ev = make_event(groups=["FrontDesk"], query_params={"propertyId": OTHER_PROP})
        assert list_folios.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_tasks(self, list_tasks, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"], query_params={"propertyId": OTHER_PROP})
        assert list_tasks.handler(ev, lambda_context)["statusCode"] == 403

    def test_room_status(self, room_status, make_event, lambda_context):
        ev = make_event(groups=["Housekeeping"], query_params={"propertyId": OTHER_PROP})
        assert room_status.handler(ev, lambda_context)["statusCode"] == 403


class TestRegionalCallerWithoutRegionIsDenied:
    """
    A regional caller whose `custom:region` claim is absent must be refused.
    Widening to the chain would make a missing claim more privileged than a
    present one — the same defect as above, on the other attribute.
    """

    def test_occupancy_report(self, occupancy_report, make_event, lambda_context):
        ev = make_event(groups=["RegionalManager"])
        assert occupancy_report.handler(ev, lambda_context)["statusCode"] == 403

    def test_range_metrics(self, range_metrics, make_event, lambda_context):
        ev = make_event(
            groups=["RegionalManager"],
            query_params={"startDate": "2026-06-01", "endDate": "2026-06-07"},
        )
        assert range_metrics.handler(ev, lambda_context)["statusCode"] == 403

    def test_list_properties(self, reporting_list_properties, make_event, lambda_context):
        ev = make_event(groups=["RegionalManager"])
        assert reporting_list_properties.handler(ev, lambda_context)["statusCode"] == 403

    def test_regional_caller_cannot_use_region_query_param_to_widen(
        self, occupancy_report, make_event, lambda_context
    ):
        """The `region` param must not substitute for a missing region claim."""
        ev = make_event(groups=["RegionalManager"], query_params={"region": "Northeast"})
        assert occupancy_report.handler(ev, lambda_context)["statusCode"] == 403


class TestLegitimateCallersStillPassTheScopeGate:
    """
    Positive control: the fix must not deny real callers.

    get_conn is stubbed to raise, so these stop at the first DB call and return
    500. A 500 here means the scope gate let the caller through, which is the
    assertion; stubbing also keeps the unit layer offline and fast (an unstubbed
    get_conn tries a real RDS IAM token call).
    """

    @staticmethod
    def _no_db(monkeypatch, handler_module):
        def _raise():
            raise RuntimeError("DB intentionally unavailable in unit tests")
        monkeypatch.setattr(handler_module, "get_conn", _raise)

    def test_chain_level_caller_passes(
        self, list_stays, make_event, lambda_context, monkeypatch
    ):
        self._no_db(monkeypatch, list_stays)
        ev = make_event(groups=["Admin"])
        assert list_stays.handler(ev, lambda_context)["statusCode"] == 500

    def test_property_scoped_caller_passes(
        self, list_stays, make_event, lambda_context, monkeypatch
    ):
        self._no_db(monkeypatch, list_stays)
        ev = make_event(groups=["FrontDesk"], property_id=PROP)
        assert list_stays.handler(ev, lambda_context)["statusCode"] == 500

    def test_regional_caller_with_region_passes(
        self, occupancy_report, make_event, lambda_context, monkeypatch
    ):
        self._no_db(monkeypatch, occupancy_report)
        ev = make_event(groups=["RegionalManager"], region="Northeast")
        assert occupancy_report.handler(ev, lambda_context)["statusCode"] == 500

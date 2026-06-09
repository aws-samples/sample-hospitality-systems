"""Unit tests for tenant isolation utilities."""

import pytest
from unittest.mock import patch
from utils.tenant import (
    get_property_id,
    get_region,
    has_group,
    require_groups,
    verify_property_access,
    get_accessible_properties,
    ForbiddenError,
)


def _make_event(property_id=None, region=None, groups=None):
    """Helper to create a mock API Gateway event with JWT claims."""
    claims = {"sub": "user-123"}
    if property_id:
        claims["custom:property_id"] = property_id
    if region:
        claims["custom:region"] = region
    if groups:
        claims["cognito:groups"] = groups
    return {"requestContext": {"authorizer": {"claims": claims}}}


class TestGetPropertyId:
    def test_returns_property_id_when_present(self):
        event = _make_event(property_id="prop-abc")
        assert get_property_id(event) == "prop-abc"

    def test_returns_none_when_absent(self):
        event = _make_event()
        assert get_property_id(event) is None

    def test_returns_none_for_empty_string(self):
        event = _make_event(property_id="")
        assert get_property_id(event) is None


class TestGetRegion:
    def test_returns_region_when_present(self):
        event = _make_event(region="Northeast")
        assert get_region(event) == "Northeast"

    def test_returns_none_when_absent(self):
        event = _make_event()
        assert get_region(event) is None


class TestHasGroup:
    def test_returns_true_when_user_in_group(self):
        event = _make_event(groups=["Admin", "Manager"])
        assert has_group(event, "Admin") is True

    def test_returns_true_when_user_in_any_group(self):
        event = _make_event(groups=["FrontDesk"])
        assert has_group(event, "Admin", "FrontDesk") is True

    def test_returns_false_when_user_not_in_group(self):
        event = _make_event(groups=["Housekeeping"])
        assert has_group(event, "Admin", "Manager") is False

    def test_handles_empty_groups(self):
        event = _make_event(groups=[])
        assert has_group(event, "Admin") is False


class TestRequireGroups:
    def test_passes_when_user_in_group(self):
        event = _make_event(groups=["FrontDesk"])
        require_groups(event, "FrontDesk", "Manager", "Admin")  # Should not raise

    def test_raises_forbidden_when_not_in_group(self):
        event = _make_event(groups=["Housekeeping"])
        with pytest.raises(ForbiddenError):
            require_groups(event, "FrontDesk", "Manager", "Admin")


class TestVerifyPropertyAccess:
    def test_chain_admin_accesses_any_property(self):
        event = _make_event(groups=["Admin"])
        verify_property_access(event, "any-property-id")  # Should not raise

    def test_chain_manager_accesses_any_property(self):
        event = _make_event(groups=["Manager"])
        verify_property_access(event, "any-property-id")  # Should not raise

    def test_property_user_accesses_own_property(self):
        event = _make_event(property_id="prop-123", groups=["FrontDesk"])
        verify_property_access(event, "prop-123")  # Should not raise

    def test_property_user_denied_other_property(self):
        event = _make_event(property_id="prop-123", groups=["FrontDesk"])
        with pytest.raises(ForbiddenError):
            verify_property_access(event, "prop-456")

    def test_regional_manager_access_granted(self):
        event = _make_event(region="Northeast", groups=["RegionalManager"])
        verify_property_access(event, "any-property")  # Should not raise

    def test_no_groups_no_property_denied(self):
        event = _make_event(groups=[])
        with pytest.raises(ForbiddenError):
            verify_property_access(event, "prop-123")


class TestGetAccessibleProperties:
    def test_property_user_gets_single_property(self):
        event = _make_event(property_id="prop-123", groups=["FrontDesk"])
        assert get_accessible_properties(event) == ["prop-123"]

    def test_chain_user_gets_none(self):
        event = _make_event(groups=["Admin"])
        assert get_accessible_properties(event) is None

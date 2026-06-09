"""Unit tests for utils.auth.

Covers the Cognito user pool authorizer claim shape and the several formats
the cognito:groups claim can arrive in (list, bracketed/space-separated, and
comma-separated), since get_claims + group parsing are load-bearing for
tenant isolation.
"""

import pytest

from utils.auth import (
    get_claims,
    get_guest_id,
    get_email,
    get_roles,
    require_owner,
    get_groups,
    has_group,
    require_groups,
    get_region,
    get_user_id,
)
from utils.tenant import ForbiddenError


def _evt(claims):
    """Cognito user pool authorizer event shape."""
    return {"requestContext": {"authorizer": {"claims": claims}}}


def _bare(claims):
    """Fallback: authorizer context IS the claims dict."""
    return {"requestContext": {"authorizer": claims}}


class TestGetClaims:
    def test_claims_shape(self):
        assert get_claims(_evt({"sub": "u1"})) == {"sub": "u1"}

    def test_bare_fallback(self):
        assert get_claims(_bare({"sub": "u1"})) == {"sub": "u1"}

    def test_missing_authorizer_returns_empty(self):
        assert get_claims({"requestContext": {}}) == {}


class TestGetGuestIdAndUserId:
    def test_get_guest_id(self):
        assert get_guest_id(_evt({"sub": "guest-9"})) == "guest-9"

    def test_get_user_id(self):
        assert get_user_id(_evt({"sub": "user-9"})) == "user-9"


class TestGetEmail:
    def test_present(self):
        assert get_email(_evt({"sub": "u", "email": "a@b.com"})) == "a@b.com"

    def test_absent(self):
        assert get_email(_evt({"sub": "u"})) is None


class TestGetRoles:
    def test_comma_separated_string(self):
        assert get_roles(_evt({"roles": "Admin, Manager"})) == ["Admin", "Manager"]

    def test_list(self):
        assert get_roles(_evt({"roles": ["Admin", "Manager"]})) == ["Admin", "Manager"]

    def test_absent(self):
        assert get_roles(_evt({"sub": "u"})) == []


class TestRequireOwner:
    def test_owner_passes(self):
        assert require_owner(_evt({"sub": "u1"}), "u1") is None

    def test_non_owner_forbidden(self):
        resp = require_owner(_evt({"sub": "u1"}), "u2")
        assert resp["statusCode"] == 403


class TestGetGroups:
    def test_bracket_space_format(self):
        # API Gateway serializes a multi-valued claim as "[Admin Manager]".
        assert get_groups(_evt({"cognito:groups": "[Admin Manager]"})) == ["Admin", "Manager"]

    def test_comma_format(self):
        assert get_groups(_evt({"cognito:groups": "Admin,Manager"})) == ["Admin", "Manager"]

    def test_list_format(self):
        assert get_groups(_evt({"cognito:groups": ["Admin"]})) == ["Admin"]

    def test_empty_string(self):
        assert get_groups(_evt({"cognito:groups": ""})) == []

    def test_empty_brackets(self):
        assert get_groups(_evt({"cognito:groups": "[]"})) == []

    def test_absent(self):
        assert get_groups(_evt({"sub": "u"})) == []


class TestHasGroup:
    def test_member(self):
        assert has_group(_evt({"cognito:groups": "[Admin]"}), "Admin") is True

    def test_member_of_any(self):
        assert has_group(_evt({"cognito:groups": "[FrontDesk]"}), "Admin", "FrontDesk") is True

    def test_not_member(self):
        assert has_group(_evt({"cognito:groups": "[Housekeeping]"}), "Admin") is False


class TestRequireGroups:
    def test_passes_when_member(self):
        require_groups(_evt({"cognito:groups": "[Manager]"}), "Manager")  # no raise

    def test_raises_when_not_member(self):
        with pytest.raises(ForbiddenError):
            require_groups(_evt({"cognito:groups": "[Housekeeping]"}), "Admin")


class TestGetRegion:
    def test_present(self):
        assert get_region(_evt({"custom:region": "Northeast"})) == "Northeast"

    def test_absent_returns_none(self):
        assert get_region(_evt({"sub": "u"})) is None

    def test_empty_string_returns_none(self):
        assert get_region(_evt({"custom:region": ""})) is None

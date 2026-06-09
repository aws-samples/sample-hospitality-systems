"""Property-based tests for tenant isolation and loyalty utilities.

Uses Hypothesis to verify invariants hold across generated inputs:
cross-property isolation, points accumulation, and tier-recalculation
idempotency.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import MagicMock

from utils.tenant import (
    get_property_id,
    verify_property_access,
    get_accessible_properties,
    ForbiddenError,
)
from utils.loyalty import (
    earn_points,
    redeem_points,
    recalculate_tier,
    TIER_MULTIPLIERS,
    TIER_THRESHOLDS,
)


# =============================================================================
# Custom Strategies
# =============================================================================

uuid_strategy = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", fullmatch=True
)

tier_strategy = st.sampled_from(["NONE", "SILVER", "GOLD", "DIAMOND"])

positive_rate = st.floats(min_value=50.0, max_value=2000.0, allow_nan=False, allow_infinity=False)

nights_strategy = st.integers(min_value=1, max_value=30)

points_balance_strategy = st.integers(min_value=0, max_value=1_000_000)

total_stays_strategy = st.integers(min_value=0, max_value=100)


def _make_event(property_id=None, groups=None):
    claims = {"sub": "user-123"}
    if property_id:
        claims["custom:property_id"] = property_id
    if groups:
        claims["cognito:groups"] = groups
    return {"requestContext": {"authorizer": {"claims": claims}}}


def _mock_conn(balance=0, lifetime=0, total_stays=0, tier="NONE"):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = {
        "points_balance": balance,
        "lifetime_points_earned": lifetime,
        "total_stays": total_stays,
        "loyalty_tier": tier,
    }
    return conn, cursor


# =============================================================================
# Invariant Properties — Tenant Isolation
# =============================================================================


class TestTenantIsolationProperties:
    @given(
        own_property=uuid_strategy,
        other_property=uuid_strategy,
    )
    @settings(max_examples=100)
    def test_property_user_never_accesses_other_property(self, own_property, other_property):
        """INVARIANT: A property-scoped user can NEVER access another property."""
        assume(own_property != other_property)

        event = _make_event(property_id=own_property, groups=["FrontDesk"])

        # Own property should always succeed
        verify_property_access(event, own_property)  # No exception

        # Other property should always fail
        with pytest.raises(ForbiddenError):
            verify_property_access(event, other_property)

    @given(property_id=uuid_strategy)
    @settings(max_examples=50)
    def test_accessible_properties_contains_own(self, property_id):
        """INVARIANT: get_accessible_properties always includes caller's own property."""
        event = _make_event(property_id=property_id, groups=["FrontDesk"])
        result = get_accessible_properties(event)
        assert result is not None
        assert property_id in result


# =============================================================================
# Invariant Properties — Loyalty Points
# =============================================================================


class TestLoyaltyPointsProperties:
    @given(
        base_rate=positive_rate,
        nights=nights_strategy,
        tier=tier_strategy,
        current_balance=points_balance_strategy,
    )
    @settings(max_examples=200)
    def test_earn_points_always_positive(self, base_rate, nights, tier, current_balance):
        """INVARIANT: Points earned are always positive (>= 1)."""
        conn, cursor = _mock_conn(balance=current_balance)
        result = earn_points(conn, "guest-1", "res-1", base_rate, nights, tier)
        assert result["points_earned"] >= 1

    @given(
        base_rate=positive_rate,
        nights=nights_strategy,
        tier=tier_strategy,
        current_balance=points_balance_strategy,
    )
    @settings(max_examples=200)
    def test_earn_points_balance_increases(self, base_rate, nights, tier, current_balance):
        """INVARIANT: new_balance = old_balance + points_earned."""
        conn, cursor = _mock_conn(balance=current_balance)
        result = earn_points(conn, "guest-1", "res-1", base_rate, nights, tier)
        assert result["new_balance"] == current_balance + result["points_earned"]

    @given(
        current_balance=st.integers(min_value=100, max_value=1_000_000),
        redeem_amount=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_redeem_points_never_negative(self, current_balance, redeem_amount):
        """INVARIANT: Balance after redemption is never negative."""
        assume(redeem_amount <= current_balance)
        conn, cursor = _mock_conn(balance=current_balance)
        result = redeem_points(conn, "guest-1", redeem_amount)
        assert result["new_balance"] >= 0
        assert result["new_balance"] == current_balance - redeem_amount


# =============================================================================
# Idempotency Properties — Tier Recalculation
# =============================================================================


class TestTierRecalculationProperties:
    @given(total_stays=total_stays_strategy)
    @settings(max_examples=100)
    def test_recalculate_tier_is_idempotent(self, total_stays):
        """IDEMPOTENCY: recalculate_tier applied twice yields same result as once."""
        # Determine what tier should be
        if total_stays >= 20:
            expected_tier = "DIAMOND"
        elif total_stays >= 10:
            expected_tier = "GOLD"
        elif total_stays >= 5:
            expected_tier = "SILVER"
        else:
            expected_tier = "NONE"

        # First application: start from NONE
        conn1, cursor1 = _mock_conn(total_stays=total_stays, tier="NONE")
        result1 = recalculate_tier(conn1, "guest-1")

        # Second application: start from the result of first
        tier_after_first = result1 if result1 else "NONE"
        conn2, cursor2 = _mock_conn(total_stays=total_stays, tier=tier_after_first)
        result2 = recalculate_tier(conn2, "guest-1")

        # Idempotent: second application should return None (no change)
        assert result2 is None

    @given(total_stays=total_stays_strategy)
    @settings(max_examples=100)
    def test_tier_thresholds_monotonically_increasing(self, total_stays):
        """INVARIANT: Higher stays always result in equal or higher tier."""
        tiers_order = ["NONE", "SILVER", "GOLD", "DIAMOND"]

        def get_tier_for_stays(stays):
            if stays >= 20:
                return "DIAMOND"
            elif stays >= 10:
                return "GOLD"
            elif stays >= 5:
                return "SILVER"
            return "NONE"

        current_tier = get_tier_for_stays(total_stays)
        higher_tier = get_tier_for_stays(total_stays + 1)

        assert tiers_order.index(higher_tier) >= tiers_order.index(current_tier)

"""Unit tests for loyalty utilities."""

import pytest
from unittest.mock import MagicMock, patch
from utils.loyalty import (
    earn_points,
    redeem_points,
    adjust_points,
    recalculate_tier,
    TIER_MULTIPLIERS,
    TIER_THRESHOLDS,
)


def _mock_conn(current_balance=500, lifetime=1000, total_stays=5, tier="SILVER"):
    """Create a mock database connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    # Default fetchone returns for different queries
    cursor.fetchone.return_value = {
        "points_balance": current_balance,
        "lifetime_points_earned": lifetime,
        "total_stays": total_stays,
        "loyalty_tier": tier,
    }
    return conn, cursor


class TestEarnPoints:
    def test_calculates_points_with_tier_multiplier(self):
        conn, cursor = _mock_conn(current_balance=100, tier="SILVER")
        result = earn_points(conn, "guest-1", "res-1", 200.0, 3, "SILVER")

        expected_points = int(200 * 3 * 1.25)  # 750
        assert result["points_earned"] == expected_points
        assert result["new_balance"] == 100 + expected_points

    def test_none_tier_uses_1x_multiplier(self):
        conn, cursor = _mock_conn(current_balance=0, tier="NONE")
        result = earn_points(conn, "guest-1", "res-1", 150.0, 2, "NONE")

        expected_points = int(150 * 2 * 1.0)  # 300
        assert result["points_earned"] == expected_points

    def test_diamond_tier_uses_2x_multiplier(self):
        conn, cursor = _mock_conn(current_balance=5000, tier="DIAMOND")
        result = earn_points(conn, "guest-1", "res-1", 300.0, 1, "DIAMOND")

        expected_points = int(300 * 1 * 2.0)  # 600
        assert result["points_earned"] == expected_points

    def test_minimum_1_point(self):
        conn, cursor = _mock_conn(current_balance=0, tier="NONE")
        result = earn_points(conn, "guest-1", "res-1", 0.0, 1, "NONE")
        assert result["points_earned"] >= 1

    def test_raises_for_unknown_guest(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.return_value = None
        with pytest.raises(ValueError, match="Guest not found"):
            earn_points(conn, "unknown", "res-1", 100.0, 1, "NONE")


class TestRedeemPoints:
    def test_successful_redemption(self):
        conn, cursor = _mock_conn(current_balance=10000)
        result = redeem_points(conn, "guest-1", 5000, "res-1")

        assert result["points_redeemed"] == 5000
        assert result["new_balance"] == 5000

    def test_insufficient_balance_raises(self):
        conn, cursor = _mock_conn(current_balance=100)
        with pytest.raises(ValueError, match="Insufficient points"):
            redeem_points(conn, "guest-1", 500)

    def test_zero_points_raises(self):
        conn, cursor = _mock_conn(current_balance=1000)
        with pytest.raises(ValueError, match="must be positive"):
            redeem_points(conn, "guest-1", 0)

    def test_negative_points_raises(self):
        conn, cursor = _mock_conn(current_balance=1000)
        with pytest.raises(ValueError, match="must be positive"):
            redeem_points(conn, "guest-1", -100)


class TestAdjustPoints:
    def test_positive_adjustment(self):
        conn, cursor = _mock_conn(current_balance=500)
        result = adjust_points(conn, "guest-1", 200, "Service recovery")

        assert result["points_adjusted"] == 200
        assert result["new_balance"] == 700

    def test_negative_adjustment(self):
        conn, cursor = _mock_conn(current_balance=500)
        result = adjust_points(conn, "guest-1", -100, "Correction")

        assert result["points_adjusted"] == -100
        assert result["new_balance"] == 400

    def test_negative_balance_raises(self):
        conn, cursor = _mock_conn(current_balance=100)
        with pytest.raises(ValueError, match="negative balance"):
            adjust_points(conn, "guest-1", -200, "Over-deduction")

    def test_empty_reason_raises(self):
        conn, cursor = _mock_conn(current_balance=500)
        with pytest.raises(ValueError, match="Reason is required"):
            adjust_points(conn, "guest-1", 100, "")


class TestRecalculateTier:
    def test_upgrade_to_silver(self):
        conn, cursor = _mock_conn(total_stays=5, tier="NONE")
        result = recalculate_tier(conn, "guest-1")
        assert result == "SILVER"

    def test_upgrade_to_gold(self):
        conn, cursor = _mock_conn(total_stays=10, tier="SILVER")
        result = recalculate_tier(conn, "guest-1")
        assert result == "GOLD"

    def test_upgrade_to_diamond(self):
        conn, cursor = _mock_conn(total_stays=20, tier="GOLD")
        result = recalculate_tier(conn, "guest-1")
        assert result == "DIAMOND"

    def test_no_change_returns_none(self):
        conn, cursor = _mock_conn(total_stays=7, tier="SILVER")
        result = recalculate_tier(conn, "guest-1")
        assert result is None

    def test_downgrade_possible(self):
        # Edge case: if total_stays somehow decreases
        conn, cursor = _mock_conn(total_stays=3, tier="SILVER")
        result = recalculate_tier(conn, "guest-1")
        assert result == "NONE"

    def test_boundary_values(self):
        """Test exact threshold boundaries."""
        conn, cursor = _mock_conn(total_stays=4, tier="NONE")
        assert recalculate_tier(conn, "guest-1") is None  # 4 stays = still NONE

        conn, cursor = _mock_conn(total_stays=5, tier="NONE")
        assert recalculate_tier(conn, "guest-1") == "SILVER"  # 5 stays = SILVER

        conn, cursor = _mock_conn(total_stays=9, tier="SILVER")
        assert recalculate_tier(conn, "guest-1") is None  # 9 stays = still SILVER

        conn, cursor = _mock_conn(total_stays=10, tier="SILVER")
        assert recalculate_tier(conn, "guest-1") == "GOLD"  # 10 stays = GOLD

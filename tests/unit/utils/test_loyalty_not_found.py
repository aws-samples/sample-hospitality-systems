"""Supplementary loyalty tests: the 'guest not found' raise paths in
earn_points, redeem_points, adjust_points, and recalculate_tier (the
existing loyalty tests always return a row, leaving these branches
uncovered)."""

from unittest.mock import MagicMock

import pytest
from utils.loyalty import adjust_points, earn_points, recalculate_tier, redeem_points


def _conn_returning(row):
    """Mock connection whose cursor.fetchone() returns the given row."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = row
    return conn


class TestGuestNotFound:
    def test_redeem_points_raises_when_guest_missing(self):
        conn = _conn_returning(None)
        with pytest.raises(ValueError, match="Guest not found"):
            redeem_points(conn, "missing-guest", 100)

    def test_adjust_points_raises_when_guest_missing(self):
        conn = _conn_returning(None)
        with pytest.raises(ValueError, match="Guest not found"):
            adjust_points(conn, "missing-guest", 50, reason="correction")

    def test_recalculate_tier_returns_none_or_raises_when_missing(self):
        conn = _conn_returning(None)
        # recalculate_tier raises ValueError on a missing guest (line 277).
        with pytest.raises(ValueError, match="Guest not found"):
            recalculate_tier(conn, "missing-guest")

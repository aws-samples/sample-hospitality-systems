"""
Loyalty utilities for the AnyCompany Hotel platform.

Handles points earning, redemption, adjustment, and tier recalculation.
All operations use SELECT FOR UPDATE to prevent concurrent overdraft.
"""

import uuid

# Tier thresholds (based on total_stays)
TIER_THRESHOLDS = {
    "DIAMOND": 20,
    "GOLD": 10,
    "SILVER": 5,
    "NONE": 0,
}

# Tier multipliers for point earning
TIER_MULTIPLIERS = {
    "NONE": 1.0,
    "SILVER": 1.25,
    "GOLD": 1.5,
    "DIAMOND": 2.0,
}

# Points required for one free night redemption
POINTS_PER_FREE_NIGHT = 10000


def earn_points(
    conn,
    guest_id: str,
    reservation_id: str | None,
    base_rate: float,
    nights: int,
    current_tier: str,
) -> dict:
    """
    Calculate and award loyalty points for a stay.

    Points formula: int(base_rate * nights * tier_multiplier)
    Uses the tier BEFORE post-stay recalculation.

    Args:
        conn: Database connection (psycopg).
        guest_id: Guest UUID.
        reservation_id: Reservation UUID (optional).
        base_rate: Nightly room rate.
        nights: Number of nights stayed.
        current_tier: Guest's tier at time of checkout.

    Returns:
        Dict with transaction_id, points_earned, new_balance.
    """
    multiplier = TIER_MULTIPLIERS.get(current_tier, 1.0)
    points = int(base_rate * nights * multiplier)

    if points <= 0:
        points = 1  # Minimum 1 point per stay

    transaction_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        # Atomic update with row lock
        cur.execute(
            "SELECT points_balance, lifetime_points_earned FROM guests "
            "WHERE guest_id = %s FOR UPDATE",
            [guest_id],
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Guest not found: {guest_id}")

        current_balance = row["points_balance"]
        new_balance = current_balance + points
        new_lifetime = row["lifetime_points_earned"] + points

        cur.execute(
            "UPDATE guests SET points_balance = %s, lifetime_points_earned = %s, "
            "updated_at = now() WHERE guest_id = %s",
            [new_balance, new_lifetime, guest_id],
        )

        cur.execute(
            "INSERT INTO loyalty_transactions "
            "(transaction_id, guest_id, reservation_id, transaction_type, points, balance_after, description) "
            "VALUES (%s, %s, %s, 'EARN_STAY', %s, %s, %s)",
            [
                transaction_id,
                guest_id,
                reservation_id,
                points,
                new_balance,
                f"Earned {points} points for {nights}-night stay (${base_rate}/night, {current_tier} tier)",
            ],
        )

    return {
        "transaction_id": transaction_id,
        "points_earned": points,
        "new_balance": new_balance,
    }


def redeem_points(
    conn,
    guest_id: str,
    points: int,
    reservation_id: str | None = None,
    description: str | None = None,
) -> dict:
    """
    Redeem loyalty points. Fails if insufficient balance.

    Uses SELECT FOR UPDATE to prevent concurrent overdraft.

    Args:
        conn: Database connection (psycopg).
        guest_id: Guest UUID.
        points: Number of points to redeem (positive integer).
        reservation_id: Optional reservation UUID for context.
        description: Optional description of redemption.

    Returns:
        Dict with transaction_id, points_redeemed, new_balance.

    Raises:
        ValueError: If insufficient points balance.
    """
    if points <= 0:
        raise ValueError("Points to redeem must be positive")

    transaction_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            "SELECT points_balance FROM guests WHERE guest_id = %s FOR UPDATE",
            [guest_id],
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Guest not found: {guest_id}")

        current_balance = row["points_balance"]
        if current_balance < points:
            raise ValueError(
                f"Insufficient points: balance={current_balance}, requested={points}"
            )

        new_balance = current_balance - points

        cur.execute(
            "UPDATE guests SET points_balance = %s, updated_at = now() WHERE guest_id = %s",
            [new_balance, guest_id],
        )

        cur.execute(
            "INSERT INTO loyalty_transactions "
            "(transaction_id, guest_id, reservation_id, transaction_type, points, balance_after, description) "
            "VALUES (%s, %s, %s, 'REDEEM_NIGHT', %s, %s, %s)",
            [
                transaction_id,
                guest_id,
                reservation_id,
                -points,
                new_balance,
                description or f"Redeemed {points} points",
            ],
        )

    return {
        "transaction_id": transaction_id,
        "points_redeemed": points,
        "new_balance": new_balance,
    }


def adjust_points(
    conn,
    guest_id: str,
    points: int,
    reason: str,
) -> dict:
    """
    Manually adjust loyalty points (positive or negative).

    For service recovery, corrections, or promotional bonuses.

    Args:
        conn: Database connection (psycopg).
        guest_id: Guest UUID.
        points: Points to add (positive) or deduct (negative).
        reason: Required reason for the adjustment.

    Returns:
        Dict with transaction_id, points_adjusted, new_balance.

    Raises:
        ValueError: If deduction would result in negative balance.
    """
    if not reason or not reason.strip():
        raise ValueError("Reason is required for point adjustments")

    transaction_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            "SELECT points_balance FROM guests WHERE guest_id = %s FOR UPDATE",
            [guest_id],
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Guest not found: {guest_id}")

        current_balance = row["points_balance"]
        new_balance = current_balance + points

        if new_balance < 0:
            raise ValueError(
                f"Adjustment would result in negative balance: "
                f"current={current_balance}, adjustment={points}"
            )

        cur.execute(
            "UPDATE guests SET points_balance = %s, updated_at = now() WHERE guest_id = %s",
            [new_balance, guest_id],
        )

        # Also update lifetime if positive adjustment
        if points > 0:
            cur.execute(
                "UPDATE guests SET lifetime_points_earned = lifetime_points_earned + %s "
                "WHERE guest_id = %s",
                [points, guest_id],
            )

        cur.execute(
            "INSERT INTO loyalty_transactions "
            "(transaction_id, guest_id, reservation_id, transaction_type, points, balance_after, description) "
            "VALUES (%s, %s, NULL, 'ADJUSTMENT', %s, %s, %s)",
            [transaction_id, guest_id, points, new_balance, reason],
        )

    return {
        "transaction_id": transaction_id,
        "points_adjusted": points,
        "new_balance": new_balance,
    }


def recalculate_tier(conn, guest_id: str) -> str | None:
    """
    Recalculate a guest's loyalty tier based on total_stays.

    Tier thresholds:
        - DIAMOND: 20+ stays
        - GOLD: 10-19 stays
        - SILVER: 5-9 stays
        - NONE: 0-4 stays

    Args:
        conn: Database connection (psycopg).
        guest_id: Guest UUID.

    Returns:
        New tier string if tier changed, None if no change.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT total_stays, loyalty_tier FROM guests WHERE guest_id = %s",
            [guest_id],
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Guest not found: {guest_id}")

        total_stays = row["total_stays"]
        current_tier = row["loyalty_tier"]

        # Determine correct tier
        if total_stays >= TIER_THRESHOLDS["DIAMOND"]:
            new_tier = "DIAMOND"
        elif total_stays >= TIER_THRESHOLDS["GOLD"]:
            new_tier = "GOLD"
        elif total_stays >= TIER_THRESHOLDS["SILVER"]:
            new_tier = "SILVER"
        else:
            new_tier = "NONE"

        if new_tier != current_tier:
            cur.execute(
                "UPDATE guests SET loyalty_tier = %s, updated_at = now() WHERE guest_id = %s",
                [new_tier, guest_id],
            )
            return new_tier

    return None

"""
Seed PMS Data for AnyCompany Hotel.

Creates guest profiles with loyalty data and booking history in the database.
Run after the Cognito users are created and the DB migration is applied.

Usage:
    python scripts/seed_pms_data.py \
        --db-host <RDS_PROXY_ENDPOINT> \
        --db-name anycompany \
        --db-password <PASSWORD>
"""

import argparse
import uuid
import random
from datetime import date, timedelta
from decimal import Decimal

# Guest data matching Cognito users
GUESTS = [
    {"email": "sarah.chen@example.com", "first_name": "Sarah", "last_name": "Chen",
     "tier": "DIAMOND", "total_stays": 25, "points_balance": 45000, "lifetime_points": 125000},
    {"email": "james.wilson@example.com", "first_name": "James", "last_name": "Wilson",
     "tier": "GOLD", "total_stays": 14, "points_balance": 22000, "lifetime_points": 68000},
    {"email": "maria.garcia@example.com", "first_name": "Maria", "last_name": "Garcia",
     "tier": "GOLD", "total_stays": 11, "points_balance": 15500, "lifetime_points": 48000},
    {"email": "david.park@example.com", "first_name": "David", "last_name": "Park",
     "tier": "SILVER", "total_stays": 7, "points_balance": 8200, "lifetime_points": 24000},
    {"email": "priya.patel@example.com", "first_name": "Priya", "last_name": "Patel",
     "tier": "SILVER", "total_stays": 5, "points_balance": 5100, "lifetime_points": 15000},
    {"email": "alex.johnson@example.com", "first_name": "Alex", "last_name": "Johnson",
     "tier": "NONE", "total_stays": 2, "points_balance": 1200, "lifetime_points": 3600},
    {"email": "emma.thompson@example.com", "first_name": "Emma", "last_name": "Thompson",
     "tier": "NONE", "total_stays": 1, "points_balance": 450, "lifetime_points": 450},
    {"email": "carlos.rivera@example.com", "first_name": "Carlos", "last_name": "Rivera",
     "tier": "NONE", "total_stays": 0, "points_balance": 0, "lifetime_points": 0},
]


def seed_guests(conn):
    """Create or update guest profiles with loyalty data."""
    print("\nSeeding guest profiles...")
    guest_ids = {}

    with conn.cursor() as cur:
        for guest in GUESTS:
            # Check if guest exists
            cur.execute("SELECT guest_id FROM guests WHERE email = %s", [guest["email"]])
            row = cur.fetchone()

            if row:
                guest_id = row["guest_id"]
                # Update loyalty fields
                cur.execute(
                    "UPDATE guests SET loyalty_tier = %s, total_stays = %s, "
                    "points_balance = %s, lifetime_points_earned = %s, updated_at = now() "
                    "WHERE guest_id = %s",
                    [guest["tier"], guest["total_stays"], guest["points_balance"],
                     guest["lifetime_points"], guest_id],
                )
                print(f"  Updated: {guest['email']} ({guest['tier']})")
            else:
                guest_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO guests "
                    "(guest_id, first_name, last_name, email, loyalty_tier, "
                    "total_stays, points_balance, lifetime_points_earned) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    [guest_id, guest["first_name"], guest["last_name"], guest["email"],
                     guest["tier"], guest["total_stays"], guest["points_balance"],
                     guest["lifetime_points"]],
                )
                print(f"  Created: {guest['email']} ({guest['tier']})")

            guest_ids[guest["email"]] = guest_id

    conn.commit()
    return guest_ids


def seed_booking_history(conn, guest_ids):
    """Create past reservations and loyalty transactions for guests with stays."""
    print("\nSeeding booking history...")

    with conn.cursor() as cur:
        # Get some property IDs
        cur.execute("SELECT property_id FROM properties LIMIT 10")
        properties = [row["property_id"] for row in cur.fetchall()]

        if not properties:
            print("  ⚠ No properties found. Run CRS seed data first.")
            return

        for guest in GUESTS:
            if guest["total_stays"] == 0:
                continue

            guest_id = guest_ids[guest["email"]]
            stays_to_create = min(guest["total_stays"], 5)  # Cap at 5 past reservations

            for i in range(stays_to_create):
                property_id = random.choice(properties)
                check_in = date.today() - timedelta(days=random.randint(30, 365))
                nights = random.randint(1, 5)
                check_out = check_in + timedelta(days=nights)
                rate = random.choice([149, 199, 249, 299, 349])
                total = rate * nights

                reservation_id = str(uuid.uuid4())

                # Create past reservation (CHECKED_OUT status)
                cur.execute(
                    "INSERT INTO reservations "
                    "(reservation_id, property_id, guest_id, room_type, "
                    "check_in_date, check_out_date, status, total_amount, "
                    "checked_in_at, checked_out_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'CHECKED_OUT', %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [reservation_id, property_id, guest_id, "STANDARD",
                     check_in, check_out, total,
                     check_in, check_out],
                )

                # Create loyalty transaction
                points = int(rate * nights * {"NONE": 1.0, "SILVER": 1.25, "GOLD": 1.5, "DIAMOND": 2.0}[guest["tier"]])
                cur.execute(
                    "INSERT INTO loyalty_transactions "
                    "(guest_id, reservation_id, transaction_type, points, "
                    "balance_after, description) "
                    "VALUES (%s, %s, 'EARN_STAY', %s, %s, %s)",
                    [guest_id, reservation_id, points, guest["points_balance"],
                     f"Earned {points} points for {nights}-night stay"],
                )

            print(f"  {guest['email']}: {stays_to_create} past reservations + loyalty transactions")

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Seed PMS data for AnyCompany Hotel")
    parser.add_argument("--db-host", required=True, help="Database host (RDS Proxy endpoint)")
    parser.add_argument("--db-name", default="anycompany", help="Database name")
    parser.add_argument("--db-user", default="anycompany_admin", help="Database user")
    parser.add_argument("--db-password", required=True, help="Database password")
    parser.add_argument("--db-port", default=5432, type=int, help="Database port")
    args = parser.parse_args()

    import psycopg
    conn = psycopg.connect(
        host=args.db_host,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
        port=args.db_port,
        row_factory=psycopg.rows.dict_row,
    )

    print(f"\n{'='*60}")
    print(f"AnyCompany Hotel PMS — Database Seeding")
    print(f"Host: {args.db_host}")
    print(f"Database: {args.db_name}")
    print(f"{'='*60}")

    try:
        guest_ids = seed_guests(conn)
        seed_booking_history(conn, guest_ids)

        print(f"\n{'='*60}")
        print("PMS data seeding complete!")
        print(f"{'='*60}\n")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

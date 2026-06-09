"""
Seed Cognito Users for AnyCompany Hotel PMS.

Creates demo guest users (with loyalty tiers) and staff users (with roles).
Run after deploying the stack to create users for testing and demos.

Usage:
    python scripts/seed_cognito_users.py \
        --user-pool-id us-east-1_XXXXXXX \
        --region us-east-1
"""

import argparse
import boto3
import json

# ==============================================================================
# Demo Guest Users (5-10 with varied loyalty tiers)
# ==============================================================================
GUEST_USERS = [
    {
        "email": "sarah.chen@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Sarah",
        "family_name": "Chen",
        "tier": "DIAMOND",
        "total_stays": 25,
        "points_balance": 45000,
        "lifetime_points": 125000,
    },
    {
        "email": "james.wilson@example.com",
        "password": "AnyCompany2026!",
        "given_name": "James",
        "family_name": "Wilson",
        "tier": "GOLD",
        "total_stays": 14,
        "points_balance": 22000,
        "lifetime_points": 68000,
    },
    {
        "email": "maria.garcia@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Maria",
        "family_name": "Garcia",
        "tier": "GOLD",
        "total_stays": 11,
        "points_balance": 15500,
        "lifetime_points": 48000,
    },
    {
        "email": "david.park@example.com",
        "password": "AnyCompany2026!",
        "given_name": "David",
        "family_name": "Park",
        "tier": "SILVER",
        "total_stays": 7,
        "points_balance": 8200,
        "lifetime_points": 24000,
    },
    {
        "email": "priya.patel@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Priya",
        "family_name": "Patel",
        "tier": "SILVER",
        "total_stays": 5,
        "points_balance": 5100,
        "lifetime_points": 15000,
    },
    {
        "email": "alex.johnson@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Alex",
        "family_name": "Johnson",
        "tier": "NONE",
        "total_stays": 2,
        "points_balance": 1200,
        "lifetime_points": 3600,
    },
    {
        "email": "emma.thompson@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Emma",
        "family_name": "Thompson",
        "tier": "NONE",
        "total_stays": 1,
        "points_balance": 450,
        "lifetime_points": 450,
    },
    {
        "email": "carlos.rivera@example.com",
        "password": "AnyCompany2026!",
        "given_name": "Carlos",
        "family_name": "Rivera",
        "tier": "NONE",
        "total_stays": 0,
        "points_balance": 0,
        "lifetime_points": 0,
    },
]

# ==============================================================================
# Staff Users (one per role)
# ==============================================================================
STAFF_USERS = [
    {
        "email": "admin@anycompanyhotels.com",
        "password": "AnyCompanyAdmin2026!",
        "given_name": "System",
        "family_name": "Admin",
        "groups": ["Admin"],
        "property_id": None,  # Chain-level
        "region": None,
    },
    {
        "email": "regional.mgr@anycompanyhotels.com",
        "password": "AnyCompanyRegional2026!",
        "given_name": "Maria",
        "family_name": "Santos",
        "groups": ["RegionalManager"],
        "property_id": None,
        "region": "Northeast",
    },
    {
        "email": "gm.newyork@anycompanyhotels.com",
        "password": "AnyCompanyGM2026!",
        "given_name": "James",
        "family_name": "Okafor",
        "groups": ["Manager"],
        "property_id": "PROPERTY_ID_PLACEHOLDER",  # Set after querying DB
        "region": None,
    },
    {
        "email": "frontdesk@anycompanyhotels.com",
        "password": "AnyCompanyFD2026!",
        "given_name": "Priya",
        "family_name": "Sharma",
        "groups": ["FrontDesk"],
        "property_id": "PROPERTY_ID_PLACEHOLDER",
        "region": None,
    },
    {
        "email": "housekeeping@anycompanyhotels.com",
        "password": "AnyCompanyHK2026!",
        "given_name": "Carlos",
        "family_name": "Rivera",
        "groups": ["Housekeeping"],
        "property_id": "PROPERTY_ID_PLACEHOLDER",
        "region": None,
    },
    {
        "email": "revenue.mgr@anycompanyhotels.com",
        "password": "AnyCompanyRevenue2026!",
        "given_name": "Sarah",
        "family_name": "Kim",
        "groups": ["RevenueManager"],
        "property_id": None,  # Chain-level
        "region": None,
    },
]


def create_user(client, user_pool_id, user_data, is_staff=False):
    """Create a Cognito user with attributes."""
    email = user_data["email"]
    print(f"  Creating user: {email}")

    attributes = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "given_name", "Value": user_data["given_name"]},
        {"Name": "family_name", "Value": user_data["family_name"]},
    ]

    if is_staff and user_data.get("property_id"):
        attributes.append({"Name": "custom:property_id", "Value": user_data["property_id"]})
    if is_staff and user_data.get("region"):
        attributes.append({"Name": "custom:region", "Value": user_data["region"]})

    try:
        client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=attributes,
            TemporaryPassword=user_data["password"],
            MessageAction="SUPPRESS",  # Don't send welcome email
        )

        # Set permanent password (skip force change)
        client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=user_data["password"],
            Permanent=True,
        )

        # Add to groups (staff only)
        if is_staff and user_data.get("groups"):
            for group in user_data["groups"]:
                client.admin_add_user_to_group(
                    UserPoolId=user_pool_id,
                    Username=email,
                    GroupName=group,
                )
                print(f"    Added to group: {group}")

        print(f"    ✓ Created successfully")
        return True

    except client.exceptions.UsernameExistsException:
        print(f"    ⚠ Already exists, skipping")
        return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Seed Cognito users for AnyCompany Hotel PMS")
    parser.add_argument("--user-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--property-id", help="Property ID for property-scoped staff users")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--staff-only", action="store_true", help="Only create staff users")
    parser.add_argument("--guests-only", action="store_true", help="Only create guest users")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    client = session.client("cognito-idp")

    print(f"\n{'='*60}")
    print(f"AnyCompany Hotel PMS — Cognito User Seeding")
    print(f"User Pool: {args.user_pool_id}")
    print(f"Region: {args.region}")
    print(f"{'='*60}\n")

    # Create guest users
    if not args.staff_only:
        print("Creating Guest Users:")
        print("-" * 40)
        for user in GUEST_USERS:
            create_user(client, args.user_pool_id, user, is_staff=False)
        print()

    # Create staff users
    if not args.guests_only:
        print("Creating Staff Users:")
        print("-" * 40)

        # Replace property_id placeholder if provided
        if args.property_id:
            for user in STAFF_USERS:
                if user["property_id"] == "PROPERTY_ID_PLACEHOLDER":
                    user["property_id"] = args.property_id

        for user in STAFF_USERS:
            create_user(client, args.user_pool_id, user, is_staff=True)
        print()

    print(f"{'='*60}")
    print("Seeding complete!")
    print(f"\nDemo Credentials:")
    print(f"  Guest (Diamond): sarah.chen@example.com / AnyCompany2026!")
    print(f"  Guest (Gold):    james.wilson@example.com / AnyCompany2026!")
    print(f"  Guest (Silver):  david.park@example.com / AnyCompany2026!")
    print(f"  Guest (None):    alex.johnson@example.com / AnyCompany2026!")
    print(f"  Staff (Admin):   admin@anycompanyhotels.com / AnyCompanyAdmin2026!")
    print(f"  Staff (FrontDesk): frontdesk@anycompanyhotels.com / AnyCompanyFD2026!")
    print(f"  Staff (Housekeeping): housekeeping@anycompanyhotels.com / AnyCompanyHK2026!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

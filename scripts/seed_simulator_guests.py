"""
Seed simulator-fodder guests for the activity simulator.

Provisions N Cognito users (default 200) and matching `guests` rows so the
activity simulator has a deep pool to attribute reservations against. The
simulator authenticates as a single Admin service user but uses an
operate-as-guest override to spread bookings across this pool.

Usage:
    pip install faker  # local dependency
    python scripts/seed_simulator_guests.py \\
        --stack anycompany-booking \\
        --user-pool-id <your-user-pool-id> \\
        --profile <your-profile> \\
        --region us-east-1 \\
        [--count 200] [--password SimulatorGuest2026!]

Idempotent: skips Cognito users that already exist (UsernameExistsException)
and DB rows whose cognito_sub already exists. Safe to re-run.
"""

import argparse
import json
import random
import sys
import uuid
import zipfile
from io import BytesIO

import boto3
from faker import Faker


LAMBDA_CODE = '''
import json
import os
import boto3

def handler(event, context):
    db_host = os.environ["DB_HOST"]
    db_name = os.environ["DB_NAME"]
    db_user = os.environ["DB_USER"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    rds = boto3.client("rds", region_name=region)
    token = rds.generate_db_auth_token(
        DBHostname=db_host, Port=5432, DBUsername=db_user, Region=region
    )

    import psycopg
    inserted = 0
    skipped = 0
    errors = []

    try:
        conn = psycopg.connect(
            host=db_host, dbname=db_name, user=db_user, password=token,
            port=5432, sslmode="require", connect_timeout=20,
        )
        for guest in event["guests"]:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO guests (
                            guest_id, cognito_sub, first_name, last_name, email,
                            email_verified, phone, nationality,
                            loyalty_tier, total_stays, points_balance, lifetime_points_earned,
                            created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            true, %s, %s,
                            %s, %s, %s, %s,
                            now(), now()
                        )
                        ON CONFLICT (cognito_sub) DO NOTHING
                        """,
                        (
                            guest["guest_id"], guest["cognito_sub"],
                            guest["first_name"], guest["last_name"], guest["email"],
                            guest.get("phone"), guest.get("nationality", "US"),
                            guest["loyalty_tier"], guest["total_stays"],
                            guest["points_balance"], guest["lifetime_points"],
                        ),
                    )
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped += 1
                conn.commit()
            except Exception as e:
                errors.append({"email": guest.get("email"), "error": str(e)})
                conn.rollback()
        conn.close()
    except Exception as e:
        return {"success": False, "error": str(e), "inserted": inserted, "skipped": skipped, "errors": errors}

    return {
        "success": True,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
'''


# Loyalty distribution: matches the seeded 8 guests' pattern.
TIER_BUCKETS = [
    # (probability, tier, stays_range, points_range, lifetime_range)
    (0.10, "DIAMOND", (20, 40),  (30000, 60000), (90000, 150000)),
    (0.20, "GOLD",    (10, 18),  (15000, 28000), (45000, 80000)),
    (0.30, "SILVER",  (4, 9),    (5000, 12000),  (15000, 35000)),
    (0.40, "NONE",    (0, 2),    (0, 1500),      (0, 3500)),
]


def pick_tier():
    """Return (tier, total_stays, points_balance, lifetime_points) sampled from TIER_BUCKETS."""
    r = random.random()
    cumulative = 0.0
    for prob, tier, stays, points, lifetime in TIER_BUCKETS:
        cumulative += prob
        if r < cumulative:
            return (
                tier,
                random.randint(*stays),
                random.randint(*points),
                random.randint(*lifetime),
            )
    # Fallback (rounding edge case)
    return ("NONE", 0, 0, 0)


def get_stack_output(cf_client, stack_name, key):
    response = cf_client.describe_stacks(StackName=stack_name)
    for output in response["Stacks"][0]["Outputs"]:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    return None


def get_nested_stack_name(cf_client, parent_stack, nested_logical_id):
    response = cf_client.describe_stack_resource(
        StackName=parent_stack, LogicalResourceId=nested_logical_id,
    )
    arn = response["StackResourceDetail"]["PhysicalResourceId"]
    return arn.split("/")[1]


def build_lambda_package():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", LAMBDA_CODE)
    return buffer.getvalue()


def create_cognito_user(client, user_pool_id, email, password, first_name, last_name):
    """Create a Cognito user. Returns the cognito_sub, or None if user already existed."""
    try:
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
            ],
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )
        client.admin_set_user_password(
            UserPoolId=user_pool_id, Username=email, Password=password, Permanent=True,
        )
        for attr in response["User"]["Attributes"]:
            if attr["Name"] == "sub":
                return attr["Value"]
        return None
    except client.exceptions.UsernameExistsException:
        # Already exists — fetch the sub
        existing = client.admin_get_user(UserPoolId=user_pool_id, Username=email)
        for attr in existing["UserAttributes"]:
            if attr["Name"] == "sub":
                return attr["Value"]
        return None


def main():
    parser = argparse.ArgumentParser(description="Seed simulator guest pool")
    parser.add_argument("--stack", required=True, help="Root CloudFormation stack name (e.g., anycompany-booking)")
    parser.add_argument("--user-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--count", type=int, default=200, help="Number of guests to seed")
    parser.add_argument("--password", default="SimulatorGuest2026!", help="Shared password for all simulator guests")
    parser.add_argument("--db-name", default="anycompany")
    parser.add_argument("--db-user", default="anycompany_admin")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    fake = Faker("en_US")

    print(f"\n{'=' * 60}")
    print(f"Seeding {args.count} simulator guests")
    print(f"Stack: {args.stack}")
    print(f"User pool: {args.user_pool_id}")
    print(f"{'=' * 60}\n")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cognito = session.client("cognito-idp")
    cf = session.client("cloudformation")
    lambda_client = session.client("lambda")

    # Step 1: provision Cognito users + collect guest records
    print("Step 1: Creating Cognito users...")
    guests = []
    for i in range(1, args.count + 1):
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"simguest-{i:03d}@example.com"
        phone = fake.phone_number()
        tier, total_stays, points_balance, lifetime_points = pick_tier()

        cognito_sub = create_cognito_user(
            cognito, args.user_pool_id, email, args.password, first_name, last_name,
        )
        if not cognito_sub:
            print(f"  [{i:03d}] ✗ {email} — could not resolve cognito_sub")
            continue

        guests.append({
            "guest_id": str(uuid.uuid4()),
            "cognito_sub": cognito_sub,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "nationality": "US",
            "loyalty_tier": tier,
            "total_stays": total_stays,
            "points_balance": points_balance,
            "lifetime_points": lifetime_points,
        })

        if i % 25 == 0:
            print(f"  [{i:03d}/{args.count}] ...")

    print(f"  Cognito users ready: {len(guests)}")

    if not guests:
        print("No users to insert. Exiting.")
        return 0

    # Step 2: collect VPC + layer + role info from CFN
    print("\nStep 2: Resolving stack resources...")
    db_host = get_stack_output(cf, args.stack, "DBProxyHost")
    vpc_stack_name = get_nested_stack_name(cf, args.stack, "VPCStack")
    private_subnets = get_stack_output(cf, vpc_stack_name, "PrivateSubnetIds").split(",")
    security_group = get_stack_output(cf, vpc_stack_name, "LambdaSecurityGroupId")

    layers = cf.list_stack_resources(StackName=args.stack)["StackResourceSummaries"]
    common_layer_arn = None
    for r in layers:
        if r["ResourceType"] == "AWS::Lambda::LayerVersion" and "CommonLayer" in r["LogicalResourceId"]:
            common_layer_arn = r["PhysicalResourceId"]
            break
    if not common_layer_arn:
        print("ERROR: Could not find CommonLayer")
        return 1

    role_resp = cf.describe_stack_resource(StackName=args.stack, LogicalResourceId="LambdaMigrationRole")
    role_name = role_resp["StackResourceDetail"]["PhysicalResourceId"]
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    # Step 3: create temporary Lambda + invoke it with the payload
    function_name = f"simulator-guest-seeder-{uuid.uuid4().hex[:8]}"
    print(f"\nStep 3: Creating temporary Lambda: {function_name}")

    zip_bytes = build_lambda_package()

    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.12",
            # Match the CommonLayer's arm64 build (else the arm64 psycopg
            # binary won't load — "no pq wrapper available").
            Architectures=["arm64"],
            Role=role_arn,
            Handler="handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=600,
            MemorySize=512,
            VpcConfig={
                "SubnetIds": private_subnets,
                "SecurityGroupIds": [security_group],
            },
            Environment={
                "Variables": {
                    "DB_HOST": db_host,
                    "DB_NAME": args.db_name,
                    "DB_USER": args.db_user,
                }
            },
            Layers=[common_layer_arn],
        )

        print("  Waiting for Lambda to be active...")
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=function_name)

        print(f"  Invoking with {len(guests)} guests...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({"guests": guests}).encode(),
        )
        result = json.loads(response["Payload"].read())

        print(f"\n{'=' * 60}")
        if result.get("success"):
            print(f"✓ Inserted: {result['inserted']}, Skipped (already existed): {result['skipped']}")
            if result.get("errors"):
                print(f"  Errors ({len(result['errors'])}):")
                for err in result["errors"][:10]:
                    print(f"    {err}")
        else:
            print(f"✗ FAILED: {result.get('error', 'Unknown error')}")
            return 1
        print(f"{'=' * 60}\n")

    finally:
        print(f"Deleting temporary Lambda: {function_name}")
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception as e:
            print(f"Warning: Could not delete Lambda: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

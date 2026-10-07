"""
Seed PMS data (loyalty profiles + booking history) via a temporary Lambda.
Uses IAM auth against RDS Proxy — no password needed.

Usage:
    python scripts/seed_pms_via_lambda.py \\
        --stack anycompany-booking \\
        --profile <your-profile> \\
        --region us-east-1
"""

import argparse
import json
import uuid
import zipfile
from io import BytesIO

import boto3

LAMBDA_CODE = '''
import json
import os
import uuid
import random
from datetime import date, timedelta
import boto3

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


def handler(event, context):
    db_host = os.environ["DB_HOST"]
    db_name = os.environ["DB_NAME"]
    db_user = os.environ["DB_USER"]
    user_pool_id = os.environ["USER_POOL_ID"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    # Fetch Cognito users to get their sub IDs
    cognito = boto3.client("cognito-idp", region_name=region)
    cognito_subs = {}
    paginator = cognito.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=user_pool_id):
        for user in page["Users"]:
            attrs = {a["Name"]: a["Value"] for a in user["Attributes"]}
            if "email" in attrs and "sub" in attrs:
                cognito_subs[attrs["email"]] = attrs["sub"]

    rds = boto3.client("rds", region_name=region)
    token = rds.generate_db_auth_token(
        DBHostname=db_host, Port=5432, DBUsername=db_user, Region=region
    )

    import psycopg

    conn = psycopg.connect(
        host=db_host, dbname=db_name, user=db_user,
        password=token, port=5432, sslmode="require", connect_timeout=20,
    )

    results = {"guests_created": 0, "guests_updated": 0, "reservations_created": 0, "loyalty_transactions": 0, "skipped_no_cognito": 0}

    try:
        with conn.cursor() as cur:
            # Get property IDs for past reservations
            cur.execute("SELECT property_id FROM properties WHERE is_active = true LIMIT 10")
            properties = [row[0] for row in cur.fetchall()]
            if not properties:
                return {"success": False, "error": "No properties found"}

            guest_ids = {}

            # Seed guest profiles
            for guest in GUESTS:
                cognito_sub = cognito_subs.get(guest["email"])
                if not cognito_sub:
                    results["skipped_no_cognito"] += 1
                    continue

                cur.execute("SELECT guest_id FROM guests WHERE email = %s", [guest["email"]])
                row = cur.fetchone()

                if row:
                    guest_id = row[0]
                    cur.execute(
                        "UPDATE guests SET loyalty_tier = %s, total_stays = %s, "
                        "points_balance = %s, lifetime_points_earned = %s, "
                        "cognito_sub = COALESCE(cognito_sub, %s), updated_at = now() "
                        "WHERE guest_id = %s",
                        [guest["tier"], guest["total_stays"], guest["points_balance"],
                         guest["lifetime_points"], cognito_sub, guest_id],
                    )
                    results["guests_updated"] += 1
                else:
                    guest_id = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO guests (guest_id, cognito_sub, first_name, last_name, email, loyalty_tier, "
                        "total_stays, points_balance, lifetime_points_earned) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [guest_id, cognito_sub, guest["first_name"], guest["last_name"], guest["email"],
                         guest["tier"], guest["total_stays"], guest["points_balance"],
                         guest["lifetime_points"]],
                    )
                    results["guests_created"] += 1

                guest_ids[guest["email"]] = guest_id

            # Seed booking history
            random.seed(42)
            for guest in GUESTS:
                if guest["total_stays"] == 0:
                    continue

                guest_id = guest_ids[guest["email"]]
                stays_to_create = min(guest["total_stays"], 5)

                for i in range(stays_to_create):
                    property_id = random.choice(properties)
                    check_in = date.today() - timedelta(days=random.randint(30, 365))
                    nights = random.randint(1, 5)
                    check_out = check_in + timedelta(days=nights)
                    rate = random.choice([149, 199, 249, 299, 349])
                    total = rate * nights

                    reservation_id = str(uuid.uuid4())

                    # Get a room_type_id for this property (random)
                    cur.execute(
                        "SELECT room_type_id FROM room_types WHERE property_id = %s LIMIT 1",
                        [property_id]
                    )
                    rt_row = cur.fetchone()
                    if not rt_row:
                        continue
                    room_type_id = rt_row[0]

                    try:
                        cur.execute(
                            "INSERT INTO reservations "
                            "(reservation_id, property_id, guest_id, room_type_id, "
                            "check_in_date, check_out_date, status, total_amount, "
                            "base_rate, adults, checked_in_at, checked_out_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, 'CHECKED_OUT', %s, %s, 2, %s, %s)",
                            [reservation_id, property_id, guest_id, room_type_id,
                             check_in, check_out, total, rate, check_in, check_out],
                        )
                        results["reservations_created"] += 1

                        multiplier = {"NONE": 1.0, "SILVER": 1.25, "GOLD": 1.5, "DIAMOND": 2.0}[guest["tier"]]
                        points = int(rate * nights * multiplier)
                        cur.execute(
                            "INSERT INTO loyalty_transactions "
                            "(guest_id, reservation_id, transaction_type, points, "
                            "balance_after, description) "
                            "VALUES (%s, %s, 'EARN_STAY', %s, %s, %s)",
                            [guest_id, reservation_id, points, guest["points_balance"],
                             "Earned " + str(points) + " points for " + str(nights) + "-night stay"],
                        )
                        results["loyalty_transactions"] += 1
                    except Exception as e:
                        # Skip on conflict (e.g., re-run)
                        conn.rollback()
                        continue

            conn.commit()

    finally:
        conn.close()

    return {"success": True, "results": results}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", default="anycompany-booking")
    parser.add_argument("--profile", help="AWS profile")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cf = session.client("cloudformation")
    lambda_client = session.client("lambda")

    # Get resources
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]}
    db_host = outputs["DBProxyHost"]
    user_pool_id = outputs["UserPoolId"]

    # VPC config
    vpc_stack_name = cf.describe_stack_resource(StackName=args.stack, LogicalResourceId="VPCStack")["StackResourceDetail"]["PhysicalResourceId"].split("/")[1]
    vpc_outputs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=vpc_stack_name)["Stacks"][0]["Outputs"]}
    private_subnets = vpc_outputs["PrivateSubnetIds"].split(",")
    sg_id = vpc_outputs["LambdaSecurityGroupId"]

    # Common layer + role
    layers = cf.list_stack_resources(StackName=args.stack)["StackResourceSummaries"]
    layer_arn = next(r["PhysicalResourceId"] for r in layers
                     if r["ResourceType"] == "AWS::Lambda::LayerVersion"
                     and "CommonLayer" in r["LogicalResourceId"])
    role_name = cf.describe_stack_resource(StackName=args.stack, LogicalResourceId="LambdaMigrationRole")["StackResourceDetail"]["PhysicalResourceId"]
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    # Build and deploy temp Lambda
    function_name = f"seed-pms-{uuid.uuid4().hex[:8]}"
    print(f"Creating temporary Lambda: {function_name}")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", LAMBDA_CODE)

    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.12",
            # Match the CommonLayer's arm64 build (else the arm64 psycopg
            # binary won't load — "no pq wrapper available").
            Architectures=["arm64"],
            Role=role_arn,
            Handler="handler.handler",
            Code={"ZipFile": buffer.getvalue()},
            Timeout=300,
            MemorySize=512,
            VpcConfig={"SubnetIds": private_subnets, "SecurityGroupIds": [sg_id]},
            Environment={"Variables": {
                "DB_HOST": db_host,
                "DB_NAME": "anycompany",
                "DB_USER": "anycompany_admin",
                "USER_POOL_ID": user_pool_id,
            }},
            Layers=[layer_arn],
        )

        print("Waiting for Lambda to be ready...")
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=function_name)

        print("Invoking seed Lambda...")
        response = lambda_client.invoke(FunctionName=function_name, Payload=b"{}")
        result = json.loads(response["Payload"].read())

        print("\n" + "=" * 60)
        if result.get("success"):
            print("✓ SUCCESS:")
            for k, v in result.get("results", {}).items():
                print(f"  {k}: {v}")
        else:
            print(f"✗ FAILED: {result.get('error', result)}")
        print("=" * 60 + "\n")

    finally:
        print(f"Deleting temporary Lambda: {function_name}")
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception as e:
            print(f"  (ignored) could not delete {function_name}: {e}")


if __name__ == "__main__":
    main()
